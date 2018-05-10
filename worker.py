"""Grammar loading and parsing to be run inside a worker process."""
import os
import re
import functools
from operator import itemgetter
from collections import OrderedDict
from discodop import treebank
from discodop.tree import Tree
from discodop.util import tokenize, workerfunc
from discodop.parser import Parser, readparam, readgrammars

PARSER = None
SHOWFUNC = True
SHOWMORPH = True
LIMIT = None
TOKENIZED = True
# POS tagged input is tokenized, and every token is of the form "word/POS"
# POS may be empty.
POSTAGS = re.compile(r'^\s*(?:\S+/\S*)(?:\s+\S+/\S*)*\s*$')

@workerfunc
def loadgrammar(directory, limit):
	"""Load grammar"""
	global PARSER, LIMIT
	params = readparam(os.path.join(directory, 'params.prm'))
	params.resultdir = directory
	readgrammars(directory, params.stages, params.postagging,
			params.transformations, top=getattr(params, 'top', 'ROOT'),
			cache=True)
	PARSER = Parser(params, loadtrees=True)
	LIMIT = limit
	print('phrasal labels', PARSER.phrasallabels)
	print('pos tags', PARSER.poslabels)
	print('function tags', PARSER.functiontags)
	print('morph tags', PARSER.morphtags)


@functools.lru_cache(maxsize=1024, typed=False)
@workerfunc
def getparses(sent,
		require=(), block=(), objfun='mpp', est='rfe', coarse='pcfg',
		root=None):
	"""Parse sentence and return a textual representation of a parse tree."""
	senttok, tags = postokenize(sent)
	if len(senttok) > LIMIT:
		return [], [], 'sentence too long', None
	PARSER.stages[-1].estimator = est
	PARSER.stages[-1].objective = objfun
	if PARSER.stages[0].mode.startswith('pcfg') and coarse:
		PARSER.stages[0].mode = (
				'pcfg' if coarse == 'pcfg-posterior' else coarse)
	results = list(PARSER.parse(
			senttok, tags=tags, require=require, block=block, root=root))
	parsetrees = results[-1].parsetrees
	parsetrees = applythreshold(parsetrees)
	parsetrees = sorted(parsetrees, key=itemgetter(1), reverse=True)
	parsetrees_ = OrderedDict()
	for treestr, prob, deriv in parsetrees:  # FIXME limit?
		tree = PARSER.postprocess(treestr, senttok, -1)[0]
		if SHOWFUNC:
			treebank.handlefunctions('add', tree, pos=True, root=True)
		if SHOWMORPH:
			domorph(tree)
		y = str(tree)
		if y in parsetrees_:
			oldprob, tree, treestr, deriv = parsetrees_[y]
			parsetrees_[y] = (prob + oldprob, tree, treestr, deriv)
		else:
			parsetrees_[y] = (prob, tree, treestr, deriv)
	# parsetrees: trees as str
	# parsetrees_: list of postprocessed ParentedTree objects
	# (may be shorter due to spurious ambiguities of state splits)
	parsetrees = sorted(parsetrees_.values(),
			key=itemgetter(0), reverse=True)
	messages = [stage.msg for stage in results]
	elapsed = [stage.elapsedtime for stage in results]
	return senttok, parsetrees, messages, elapsed


@workerfunc
def augment(trees, sents):
	"""Add trees/sentences to this worker's grammar."""
	PARSER.augmentgrammar(trees, sents)
	getparses.cache_clear()


@workerfunc
def getprop(name):
	"""Read an attribute of the Parser object."""
	return getattr(PARSER, name)


def postokenize(sent):
	"""Tokenize sentence; extract POS tags if given."""
	if POSTAGS.match(sent):
		senttok, tags = zip(*(a.rsplit('/', 1) for a in sent.split()))
	elif TOKENIZED:
		senttok, tags = tuple(sent.split(' ')), None
	else:
		senttok, tags = tuple(tokenize(sent)), None
	if not senttok:  # or not 1 <= len(senttok) <= app.config['LIMIT']:
		raise ValueError('no sentence')
		#		'Sentence too long: %d words, max %d' % (
		#		len(senttok), app.config['LIMIT']))
	return senttok, tags


def applythreshold(parsetrees):
	"""Return parse trees with a normalized prob ``p > 1 / len(parsetrees)``.
	"""
	if not parsetrees or len(parsetrees) <= 3:
		return parsetrees
	probmass = sum(a[1] for a in parsetrees)
	threshold = 1 / len(parsetrees)
	return [a for a in parsetrees if a[1] / probmass > threshold]


def domorph(tree):
	"""Replace POS tags with morphological tags if available."""
	for node in tree.subtrees(
			lambda n: n and not isinstance(n[0], Tree)):
		x = (node.source[treebank.MORPH]
				if hasattr(node, 'source') and node.source else None)
		if x and x != '--':
			treebank.handlemorphology('add', None, node, node.source)

if __name__ == '__main__':
	pass
