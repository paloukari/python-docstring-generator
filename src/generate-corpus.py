#! /usr/bin/python

import sys
import ast
import re
import os

import astunparse
import click
import multiprocessing
import pickle

from glob import glob, iglob
from pathlib import Path
from joblib import Parallel, delayed


def prettify_docstring(docstr):
    docstr = docstr.replace("DCQT", "DCQTDCQT").replace("DCNL", "DCQTDCNL")
    docstr = docstr.replace("'", "\\'")
    rv_list = []
    for line in docstr.split('\n'):
        line = line.strip()  	# Remove whitespaces on both ends of a line
        if (line == "") or (not any([c.isalnum() for c in line])):
            # Drop empty and completely non-alphanumeric lines (e.g. lines consisting only of separatos like ----------)
            continue
        rv_list.append(line)
    unevaluated_pretty_docstring = "'" + " DCNL ".join(rv_list) + "'"
    return unevaluated_pretty_docstring

# reduce identation to one space (or custom separator) per level
# assumes that the original code uses 4 spaces per level


def reduce_ident(line, ident_separator=" "):
    line = line.rstrip()
    line_all_stripped = line.lstrip()
    n_spaces = len(line) - len(line_all_stripped)
    n_ident = int(n_spaces / 4)
    return (ident_separator * n_ident) + line_all_stripped


def escape_control_strings(s):
    return s.replace("DCQT", "DCQTDCQT").replace("DCNL", "DCQTDCNL")


def inplace_escape_spaces_in_strings(node):
    if isinstance(node, ast.Str):
        node.s = node.s.replace("DCQS", "DCQSDCQS").replace(" DCSP ", " DCQSDCSP ").replace(
            " DCTB ", " DCQSDCTB ").replace(" ", " DCSP ").replace("\t", " DCTB ")
    else:
        for child in ast.iter_child_nodes(node):
            inplace_escape_spaces_in_strings(child)


def process_function(node, corpus, input_filename, parent_class_lineno):
    docstr = ast.get_docstring(node)
    if docstr == None:
        return
    # Bail if it's in chinese. Remove all other non-english docstrings
    if len(re.findall(r'[\u4e00-\u9fff]+', docstr)) > 0:
        return
    inplace_escape_spaces_in_strings(node)
    unparsed_list = astunparse.unparse(node).split('\n')
    n_funcdef_decorators = len(node.decorator_list)
    unparsed_funcdef = unparsed_list[2:3 + n_funcdef_decorators]
    unparsed_body = unparsed_list[4 + n_funcdef_decorators:]
    pretty_docstring = prettify_docstring(docstr)
    funcdef = " DCNL ".join([escape_control_strings(line)
                             for line in unparsed_funcdef])
    processed_body = []
    for line in unparsed_body:
        if line == "":
            continue 		# Drop empty lines
        line = escape_control_strings(line)
        line = reduce_ident(line, ident_separator=" DCSP ")
        processed_body.append(line)
    processed_body_str = ' DCNL'.join(processed_body)
    meta_str = input_filename + " " + \
        str(node.lineno) + (" " + str(parent_class_lineno)
                            if parent_class_lineno > -1 else "")
    if (pretty_docstring == "") or (processed_body_str == "") or (funcdef == ""):
        return
    corpus.append([funcdef, processed_body_str, pretty_docstring, meta_str])
    print(len(corpus))


def process_class(node, corpus, input_filename, parent_class_lineno):
    for inner_node in node.body:
        if isinstance(inner_node, ast.ClassDef):
            process_class(inner_node, corpus, input_filename, node.lineno)
        elif isinstance(inner_node, ast.FunctionDef):
            process_function(inner_node, corpus, input_filename, node.lineno)


def process_module(in_fd, corpus, input_filename, methods):
    module_str = in_fd.read()
    module_ast = ast.parse(module_str)
    for node in module_ast.body:
        if methods and isinstance(node, ast.ClassDef):
            process_class(node, corpus, input_filename, -1)
        else:
            if isinstance(node, ast.FunctionDef):
                process_function(node, corpus, input_filename, -1)


def _process_file(file, corpus, input_filename, methods):
    try:
        with open(file) as input:
            process_module(input, corpus, input_filename, methods)
    except SyntaxError:
        print("Can't parse file:" + input_filename)
    except Exception as ex:
        print("Can't process file:" + input_filename)


def generate(input_path, indices, regen, output_file, methods, singlethreaded):
    corpus = []

    if not input_path.endswith('/'):
        input_path = input_path + '/'
    if not os.path.isabs(input_path):
        input_path = os.path.realpath(input_path)

    if not os.path.isabs(output_file):
        output_file = os.path.realpath(output_file)

    if not os.path.isabs(indices):
        indices = os.path.realpath(indices)
    print("Generating corpus in %s" % output_file)

    if not os.path.exists(indices) or regen:
        base_len = len(input_path)+1
        python_files = [y[base_len:] for x in os.walk(
            input_path) for y in iglob(os.path.join(x[0], '*.py'))]

        with open(indices, 'wb') as indices:
            pickle.dump(python_files, indices)
    else:
        with open(indices, 'rb') as indices:
            python_files = pickle.load(indices)

    if singlethreaded:
        for filename in python_files:
            _process_file(os.path.join(input_path, filename), corpus, filename, methods)
    else:
        num_cores = multiprocessing.cpu_count()
        results = Parallel(n_jobs=2*num_cores)(
            delayed(_process_file)(os.path.join(input_path, filename), corpus, filename, methods) for filename in python_files)

    with open(output_file, "wb") as outfile:
        pickle.dump(corpus, outfile)


@click.command()
@click.option('-i', '--input', default='./.data/repos', show_default=True, required=True,
              help="Directory into which repos are cloned.")
@click.option('-x', '--indices', default='./.data/py.pickle', show_default=True, required=True,
              help="File indices of the input directory.")
@click.option('-o', '--output', default='./.data/corpus.functions.pickle', show_default=True, required=True,
              help="Output file to save the corpus to.")
@click.option('-r', '--regen', default=False, is_flag=True, show_default=True,
              help="Regenerates the indices file.")
@click.option('-s', '--methods', default=False, is_flag=True, show_default=True,
              help="Generates the corpus from the methods (vs functions).")
@click.option('-s', '--singlethreaded', default=False, is_flag=True, show_default=True,
              help="Executes in singlethreaded mode.")
def main(input, indices, regen, output, methods, singlethreaded):
    generate(input, indices, regen, output, methods, singlethreaded)


if __name__ == "__main__":
    main()
