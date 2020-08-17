import gffutils
from multiprocessing import Pool
from pyfaidx import Fasta, Faidx
from functools import partial
import liftoff_utils
import os


def extract_features_to_lift(g_arg, db_arg, ref_chroms, reference_fasta, processes, infer_transcripts, infer_genes, inter_files, liftover_type, parent_types_to_list):
    print("extracting features")
    if os.path.exists(inter_files) is False:
        os.mkdir(inter_files)
    feature_db, feature_db_name = create_feature_db_connections(g_arg, db_arg, infer_transcripts, infer_genes)
    parent_dict, child_dict, intermediate_dict, parent_order= seperate_parents_and_children(feature_db, parent_types_to_list)
    get_gene_sequences(parent_dict, ref_chroms, reference_fasta, processes, inter_files, liftover_type)
    return parent_dict, child_dict, intermediate_dict, feature_db, parent_order


def create_feature_db_connections(g_arg, db_arg, infer_transcripts, infer_genes):
    if infer_transcripts is True:
        disable_transcripts = False
    else:
        disable_transcripts = True
    if infer_genes is True:
        disable_genes = False
    else:
        disable_genes = True
    if db_arg is None:
        feature_db = gffutils.create_db(g_arg, g_arg + "_db", merge_strategy="create_unique", force=True,
                                 disable_infer_transcripts=disable_transcripts, disable_infer_genes=disable_genes, verbose=True)
        feature_db_name = db_arg
    else:
        feature_db = gffutils.FeatureDB(db_arg)
        feature_db_name = db_arg
    return feature_db, feature_db_name



def seperate_parents_and_children(feature_db, parent_types_to_lift):
    parent_dict, child_dict, intermediate_dict = {} , {}, {}
    feature_types = feature_db.featuretypes()
    parent_types, child_types, intermediate_types = find_feature_type_order(feature_types, feature_db)
    feature_num = 0
    filtered_parents = [parent for parent in parent_types if parent in parent_types_to_lift]
    for parent_type in filtered_parents:
        for parent in feature_db.features_of_type(featuretype=parent_type):
            feature_num += 1
            parent_dict[parent.id] = parent
            child_dict[parent.id] = []
            for child_type in child_types:
                for child in feature_db.children(parent, featuretype=child_type):
                    child_dict[parent.id].append(child)
                    if "Parent" not in child.attributes:
                        add_parent_tag(child, feature_db)
            if len(child_dict[parent.id]) == 0:
                child_dict[parent.id].append(parent)
    for intermediate_type in intermediate_types:
        for intermediate_feature in feature_db.features_of_type(featuretype=intermediate_type):
            intermediate_dict[intermediate_feature.id] = intermediate_feature
            if "Parent" not in intermediate_feature.attributes:
                add_parent_tag(intermediate_feature, feature_db)
    parent_order = liftoff_utils.find_parent_order(
        [parent for parent in list(parent_dict.values()) if parent is not None])
    return parent_dict, child_dict, intermediate_dict, parent_order


def add_parent_tag(feature, feature_db):
    parent_id = ""
    parents = list(feature_db.parents(feature, level=1))
    if len(parents) > 0:
        parent_id = parents[0].id
    else:
        parents = list(feature_db.parents(feature))
        if len(parents) > 0:
            parent_id = parents[0].id
    feature.attributes["Parent"]= parent_id


def find_feature_type_order(feature_types, feature_db):
    parent_types, intermediate_types, child_types = [],[],[]
    for feature_type in feature_types:
        if feature_type != "region":
            for feature in feature_db.features_of_type(featuretype=feature_type):
                is_child = has_child(feature, feature_db) is False
                is_parent = has_parent(feature, feature_db) is False
                if is_child:
                    child_types.append(feature_type)
                if is_parent:
                    parent_types.append(feature_type)
                if is_parent is False and is_child is False:
                    intermediate_types.append(feature_type)
                break
    return parent_types, child_types, intermediate_types



def has_parent(feature, feature_db):
    for parent in feature_db.parents(feature.id, level=1):
        if feature.id != parent.id:
            return True
    return False


def has_child(feature, feature_db):
    for child in feature_db.children(feature.id):
        return True
    return False



def get_gene_sequences(parent_dict, ref_chroms, reference_fasta_name, processes, inter_files, liftover_type):
    pool = Pool(processes)
    Faidx(reference_fasta_name)
    if liftover_type == "unplaced":
        open(inter_files+"/unplaced_genes.fa", 'w')
    func = partial(get_gene_sequences_subset, parent_dict, reference_fasta_name, inter_files, liftover_type)
    for result in pool.imap_unordered(func, ref_chroms):
        continue
    pool.close()
    pool.join()
    return


def get_gene_sequences_subset(parent_dict, reference_fasta_name,  inter_files, liftover_type, chrom_name):
    reference_fasta = Fasta(reference_fasta_name)
    if chrom_name  == reference_fasta_name and (liftover_type == "chrm_by_chrm" or liftover_type == "copies"):
        fasta_out_name = "reference_all"
    elif liftover_type == "unmapped":
        fasta_out_name = "unmapped_to_expected_chrom"
    elif liftover_type == "unplaced":
        fasta_out_name = "unplaced"
    else:
        fasta_out_name = chrom_name
    if liftover_type == "unplaced":
        fasta_out = open(inter_files+"/"+fasta_out_name + "_genes.fa", 'a')
    else:
        fasta_out = open(inter_files+"/"+fasta_out_name + "_genes.fa", 'w')
    sorted_parents = sorted(list(parent_dict.values()), key=lambda x: x.seqid)
    if chrom_name == reference_fasta_name:
        current_chrom = sorted_parents[0].seqid
    else:
        current_chrom = chrom_name
    chrom_seq = reference_fasta[current_chrom]
    for parent in sorted_parents:
        if parent.seqid != current_chrom and chrom_name == reference_fasta_name:
            current_chrom=parent.seqid
            chrom_seq = reference_fasta[current_chrom]
        if parent.seqid == chrom_name or chrom_name == reference_fasta_name:
            parent_seq = chrom_seq[parent.start-1: parent.end].seq
            fasta_out.write(">" + parent.id + "\n" + str(parent_seq) + "\n")
    fasta_out.close()
    return





