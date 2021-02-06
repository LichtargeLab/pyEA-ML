#!/usr/bin/env python
import re
from itertools import product

import numpy as np
import pandas as pd
from pysam import VariantFile


def parse_gene(vcf_fn, gene, gene_reference, samples, min_af=None, max_af=None, af_field='AF', EA_parser='all'):
    feature_names = ('D1', 'D30', 'D70', 'R1', 'R30', 'R70')
    ft_cutoffs = list(product((1, 2), (1, 30, 70)))
    vcf = VariantFile(vcf_fn)
    vcf.subset_samples(samples)
    if type(gene_reference) == pd.DataFrame:
        contig = gene_reference['chrom'].iloc[0].strip('chr')
    else:
        contig = gene_reference['chrom'].strip('chr')
    cds_start = gene_reference['cdsStart'].min()
    cds_end = gene_reference['cdsEnd'].max()
    canon_nm = get_canon_nm(gene_reference)
    gene_df = pd.DataFrame(np.ones((len(samples), 6)), index=samples, columns=('D1', 'D30', 'D70', 'R1', 'R30', 'R70'))

    for rec in fetch_variants(vcf, contig=contig, start=cds_start, stop=cds_end):
        ea = refactor_EA(rec.info['EA'], rec.info['NM'], canon_nm, EA_parser=EA_parser)

        pass_af_check = af_check(rec, af_field=af_field, max_af=max_af, min_af=min_af)
        if ea and gene == rec.info['gene'] and pass_af_check:
            continue
        gts = pd.Series([convert_zygo(rec.samples[sample]['GT']) for sample in samples], index=samples, dtype=int)
        for i, ft_name in enumerate(feature_names):
            cutoff = ft_cutoffs[i]
            for score in ea:
                mask = (score >= cutoff[1]) & (gts >= cutoff[0])
                gene_df[ft_name] *= (1 - (score * mask) / 100)**gts
    return 1 - gene_df


# util functions
def fetch_variants(vcf, contig=None, start=None, stop=None):
    """
    Iterates over all variants (splitting variants with overlapping gene annotations).

    Args:
        vcf (VariantFile): pysam VariantFile
        contig (str): Chromosome of interest
        start (int): The starting nucleotide position of the region of interest
        stop (int): The ending nucleotide position of the region of interest

    Yields:
        VariantRecord
    """
    for rec in vcf.fetch(contig=contig, start=start, stop=stop):
        if type(rec.info['gene']) == tuple:  # check for overlapping gene annotations
            for var in split_genes(rec):
                yield var
        else:
            yield rec


def get_canon_nm(gene_reference):
    if type(gene_reference) == pd.DataFrame:
        nm_numbers = [int(nm.strip('NM_')) for nm in list(gene_reference['name'])]
        minpos = np.argmin(nm_numbers)
        return gene_reference['name'].iloc[minpos]
    else:
        return gene_reference['name']


def af_check(rec, af_field='AF', max_af=None, min_af=None):
    if max_af is None and min_af is None:
        return True
    elif max_af is None:
        max_af = 1
    elif min_af is None:
        min_af = 0
    af = rec.info[af_field]
    if type(af) == tuple:
        af = af[0]
    return min_af < af < max_af


def split_genes(rec):
    """
    If a variant has overlapping gene annotations, it will be split into separate records with correct corresponding
    transcripts, substitutions, and EA scores.

    Args:
        rec (VariantRecord)

    Yields:
        VariantRecord
    """
    def _gene_map(gene_idxs, values):
        genes = gene_idxs.keys()
        if len(values) == len([i for l in gene_idxs.values() for i in l]):
            val_d = {g: [values[i] for i in gene_idxs[g]] for g in genes}
        elif len(values) == 1:
            val_d = {g: values for g in genes}
        else:
            raise ValueError('Size of values list does not match expected case.')
        return val_d

    ea = rec.info['EA']
    gene = rec.info['gene']
    geneset = set(gene)
    idxs = {genekey: [i for i, g in enumerate(gene) if g == genekey] for genekey in geneset}
    ea_d = _gene_map(idxs, ea)
    for g in geneset:
        var = rec.copy()
        var.info['gene'] = g
        var.info['EA'] = tuple(ea_d[g])
        yield var


def refactor_EA(EA, nm_ids, canon_nm, EA_parser='all'):
    """
    Refactors EA to a list of floats and NaN.

    Args:
        EA (list/tuple): The EA scores parsed from a variant
        nm_ids (list/tuple): Transcript IDs corresponding to EA scores
        canon_nm (str): Canonical NM ID based on smallest numbered transcript
        EA_parser (str): How to aggregate multiple transcript scores

    Returns:
        list: The new list of scores, refactored as float or NaN

    Note: EA must be string type, otherwise regex search will raise an error.
    """
    newEA = []
    if EA_parser == 'canonical' and canon_nm in nm_ids:
        return EA[nm_ids.index(canon_nm)]
    else:
        for score in EA:
            try:
                score = float(score)
            except (ValueError, TypeError):
                if re.search(r'fs-indel', score) or re.search(r'STOP', score):
                    score = 100
                else:
                    continue
            newEA.append(score)
        if EA_parser == 'mean':
            return np.nanmean(newEA)
        elif EA_parser == 'max':
            return np.nanmax(newEA)
        elif EA_parser == 'min':
            return np.nanmin(newEA)
        else:
            return newEA


def convert_zygo(genotype):
    """
    Converts a genotype tuple to a zygosity integer.

    Args:
        genotype (tuple): The genotype of a variant for a sample

    Returns:
        int: The zygosity of the variant (0/1/2)
    """
    if genotype in [(1, 0), (0, 1), ('.', 1), (1, '.')]:
        zygo = 1
    elif genotype == (1, 1):
        zygo = 2
    else:
        zygo = 0
    return zygo
