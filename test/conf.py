#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, os.path.abspath('..'))

extensions = ['sphinx-gobject', 'sphinx.ext.githubpages']
source_suffix = '.rst'
master_doc = 'index'
project = 'Test'
copyright = '2017, Test'
author = 'Test'
version = '0'
release = '0'
language = None
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
pygments_style = 'sphinx'
todo_include_todos = False
html_theme = 'sphinx_rtd_theme'
