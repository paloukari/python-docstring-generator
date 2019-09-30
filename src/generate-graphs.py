
import textwrap
import re
import os
import json
import click
import pickle
import multiprocessing

from ast import parse
from collections import defaultdict
from ast_graph_generator import AstGraphGenerator
from joblib import Parallel, delayed

# Extracts function names


def decl_tokenizer(decl):
    function_name = re.search('(?<=def )[\w_-]+(?=\(.*\):)', decl).group(0)
    return splitter(function_name)


# Tokenize on spaces and around delimiters.
# Keep delimiters together only if it makes sense (e.g. parentheses, dots)
docstring_regex_tokenizer = re.compile(
    r"[^\s,'\"`.():\[\]=*;>{\}+-/\\]+|\\+|\.+|\(\)|{\}|\[\]|\(+|\)+|:+|\[+|\]+|{+|\}+|=+|\*+|;+|>+|\++|-+|/+")


def docstring_tokenize(docstr: str):
    return [t for t in docstring_regex_tokenizer.findall(docstr) if t is not None and len(t) > 0]


def process_body(idx, total, body, docstring):
    errors = 0
    doc_tokenizer = docstring_tokenize
    try:
        if idx % 100 == 0:
            print('%.1f %%    \r' % (idx / float(total) * 100), end="")

        visitor = AstGraphGenerator()

        visitor.visit(parse(body))

        edge_list = [(t, origin, destination)
                     for (origin, destination), edges
                     in visitor.graph.items() for t in edges]

        docs_words = doc_tokenizer(docstring)

        graph_node_labels = [label.strip() for (
            _, label) in sorted(visitor.node_label.items())]

        return {"edges": edge_list,
                "backbone_sequence": visitor.terminal_path,
                "node_labels": graph_node_labels,
                "docs_words": docs_words}

    except Exception as e:
        errors += 1

    return None


def process_data(inputs, outputs, singlethreaded):
    data = []

    num_inits = 0
    errors = 0

    total = len(inputs)

    if singlethreaded:
        for idx, (body, docstring) in enumerate(zip(inputs, outputs)):
            data.append(process_body(idx, total, body,
                                     docstring))
    else:
        num_cores = multiprocessing.cpu_count()
        data = Parallel(n_jobs=2*num_cores)(
            delayed(process_body)(idx, total, body, docstring) for idx, (body, docstring) in enumerate(zip(inputs, outputs)))

    
    data = [x for x in data if x is not None]

    print("Generated %d graphs out of %d snippets" %
          (len(data), len(inputs)))

    return data


@click.command()
@click.option('-i', '--input', default='./.data/corpus.functions.pickle', show_default=True, required=True,
              help="Corpus file to process.")
@click.option('-o', '--output', default='./.data/corpus.functions.pickle', show_default=True, required=True,
              help="Output file to save the processed corpus to.")
@click.option('-s', '--singlethreaded', default=False, is_flag=True, show_default=True,
              help="Executes in singlethreaded mode.")
def main(input, output, singlethreaded):

    if not os.path.isabs(input):
        input = os.path.realpath(input)
    if not os.path.isabs(output):
        output = os.path.realpath(output)

    with open(input, 'rb') as input_file:
        corpus = pickle.load(input_file)

    # unident body so it can be parsed
    code = [textwrap.dedent(record[1].replace("DCNL ", "\n").replace(
        " DCSP ", "\t").replace("DCSP ", "\t")) for record in corpus]

    docstring = [record[2].replace("DCNL ", "\n").replace(
        "DCSP ", "\t") for record in corpus]

    assert len(docstring) == len(code)

    data = process_data(code, docstring, singlethreaded)

    with open(output, 'wb') as output_file:
        pickle.dump(data, output_file)


if __name__ == "__main__":
    main()
