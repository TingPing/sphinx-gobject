# -*- coding: utf-8 -*-
"""
    sphinx.domains.python
    ~~~~~~~~~~~~~~~~~~~~~

    The Python domain.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re

from six import iteritems
from docutils import nodes
from docutils.parsers.rst import directives

from sphinx import addnodes
from sphinx.roles import XRefRole
from sphinx.locale import l_, _
from sphinx.domains import Domain, ObjType, Index
from sphinx.directives import ObjectDescription
from sphinx.util.nodes import make_refnode
from sphinx.util.compat import Directive
from sphinx.util.docfields import Field, GroupedField, TypedField


# REs for Python signatures
py_sig_re = re.compile(
    r'''^ ([\w.]*\.)?            # class name(s)
          ([\w-]+)  \s*             # thing name
          (?: \((.*)\)           # optional: arguments
           (?:\s* -> \s* (.*))?  #           return annotation
          )? $                   # and nothing more
          ''', re.VERBOSE)


def _pseudo_parse_arglist(signode, arglist):
    """"Parse" a list of arguments separated by commas.

    Arguments can have "optional" annotations given by enclosing them in
    brackets.  Currently, this will split at any comma, even if it's inside a
    string literal (e.g. default argument value).
    """
    paramlist = addnodes.desc_parameterlist()
    stack = [paramlist]
    try:
        for argument in arglist.split(','):
            argument = argument.strip()
            ends_open = ends_close = 0
            while argument.startswith('['):
                stack.append(addnodes.desc_optional())
                stack[-2] += stack[-1]
                argument = argument[1:].strip()
            while argument.startswith(']'):
                stack.pop()
                argument = argument[1:].strip()
            while argument.endswith(']') and not argument.endswith('[]'):
                ends_close += 1
                argument = argument[:-1].strip()
            while argument.endswith('['):
                ends_open += 1
                argument = argument[:-1].strip()
            if argument:
                stack[-1] += addnodes.desc_parameter(argument, argument)
            while ends_open:
                stack.append(addnodes.desc_optional())
                stack[-2] += stack[-1]
                ends_open -= 1
            while ends_close:
                stack.pop()
                ends_close -= 1
        if len(stack) != 1:
            raise IndexError
    except IndexError:
        # if there are too few or too many elements on the stack, just give up
        # and treat the whole argument list as one argument, discarding the
        # already partially populated paramlist node
        signode += addnodes.desc_parameterlist()
        signode[-1] += addnodes.desc_parameter(arglist, arglist)
    else:
        signode += paramlist


# This override allows our inline type specifiers to behave like :class: link
# when it comes to handling "." and "~" prefixes.
class PyXrefMixin(object):
    def make_xref(self, rolename, domain, target, innernode=nodes.emphasis,
                  contnode=None):
        result = super(PyXrefMixin, self).make_xref(rolename, domain, target,
                                                    innernode, contnode)
        result['refspecific'] = True
        if target.startswith(('.', '~')):
            prefix, result['reftarget'] = target[0], target[1:]
            if prefix == '.':
                text = target[1:]
            elif prefix == '~':
                text = target.split('.')[-1]
            for node in result.traverse(nodes.Text):
                node.parent[node.parent.index(node)] = nodes.Text(text)
                break
        return result

    def make_xrefs(self, rolename, domain, target, innernode=nodes.emphasis,
                   contnode=None):
        delims = '(\s*[\[\]\(\),](?:\s*or\s)?\s*|\s+or\s+)'
        delims_re = re.compile(delims)
        sub_targets = re.split(delims, target)

        split_contnode = bool(contnode and contnode.astext() == target)

        results = []
        for sub_target in sub_targets:
            if split_contnode:
                contnode = nodes.Text(sub_target)

            if delims_re.match(sub_target):
                results.append(contnode or innernode(sub_target, sub_target))
            else:
                results.append(self.make_xref(rolename, domain, sub_target,
                                              innernode, contnode))

        return results


class PyField(PyXrefMixin, Field):
    pass


class PyGroupedField(PyXrefMixin, GroupedField):
    pass


class PyTypedField(PyXrefMixin, TypedField):
    pass


class PyObject(ObjectDescription):
    """
    Description of a general Python object.
    """
    option_spec = {
        'noindex': directives.flag,
        'module': directives.unchanged,
        'annotation': directives.unchanged,
    }

    doc_field_types = [
        PyTypedField('parameter', label=l_('Parameters'),
                     names=('param', 'parameter', 'arg', 'argument',
                            'keyword', 'kwarg', 'kwparam'),
                     typerolename='obj', typenames=('paramtype', 'type'),
                     can_collapse=True),
        PyTypedField('variable', label=l_('Variables'), rolename='obj',
                     names=('var', 'ivar', 'cvar'),
                     typerolename='obj', typenames=('vartype',),
                     can_collapse=True),
        Field('returnvalue', label=l_('Returns'), has_arg=False,
              names=('returns', 'return')),
        PyField('returntype', label=l_('Return type'), has_arg=False,
                names=('rtype',), bodyrolename='obj'),
    ]

    def get_signature_prefix(self, sig):
        """May return a prefix to put before the object name in the
        signature.
        """
        return ''

    def needs_arglist(self):
        """May return true if an empty argument list is to be generated even if
        the document contains none.
        """
        return False

    def handle_signature(self, sig, signode):
        """Transform a Python signature into RST nodes.

        Return (fully qualified name of the thing, classname if any).

        If inside a class, the current class name is handled intelligently:
        * it is stripped from the displayed name if present
        * it is added to the full name (return value) if not present
        """
        m = py_sig_re.match(sig)
        if m is None:
            raise ValueError
        name_prefix, name, arglist, retann = m.groups()

        # determine module and class name (if applicable), as well as full name
        modname = self.options.get(
            'module', self.env.ref_context.get('gobject:module'))
        classname = self.env.ref_context.get('gobject:class')
        if not classname:
            classname = self.env.ref_context.get('gobject:interface')
        if not classname:
            classname = self.env.ref_context.get('gobject:enum')
        if classname:
            add_module = False
            if name_prefix and name_prefix.startswith(classname):
                fullname = name_prefix + name
                # class name is given again in the signature
                name_prefix = name_prefix[len(classname):].lstrip('.')
            elif name_prefix:
                # class name is given in the signature, but different
                # (shouldn't happen)
                fullname = classname + '.' + name_prefix + name
            else:
                # class name is not given in the signature
                fullname = classname + '.' + name
        else:
            add_module = True
            if name_prefix:
                classname = name_prefix.rstrip('.')
                fullname = name_prefix + name
            else:
                classname = ''
                fullname = name

        signode['module'] = modname
        signode['class'] = classname
        signode['fullname'] = fullname

        sig_prefix = self.get_signature_prefix(sig)
        if sig_prefix:
            signode += addnodes.desc_annotation(sig_prefix, sig_prefix)

        if name_prefix:
            signode += addnodes.desc_addname(name_prefix, name_prefix)
        elif add_module and self.env.config.add_module_names:
            modname = self.options.get(
                'module', self.env.ref_context.get('gobject:module'))
            if modname:
                nodetext = modname + '.'
                signode += addnodes.desc_addname(nodetext, nodetext)

        anno = self.options.get('annotation')

        signode += addnodes.desc_name(name, name)
        if not arglist:
            if self.needs_arglist():
                # for callables, add an empty parameter list
                signode += addnodes.desc_parameterlist()
            if retann:
                signode += addnodes.desc_returns(retann, retann)
            if anno:
                signode += addnodes.desc_annotation(' ' + anno, ' ' + anno)
            return fullname, name_prefix

        _pseudo_parse_arglist(signode, arglist)
        if retann:
            signode += addnodes.desc_returns(retann, retann)
        if anno:
            signode += addnodes.desc_annotation(' ' + anno, ' ' + anno)
        return fullname, name_prefix

    def get_index_text(self, modname, name):
        """Return the text for the index entry of the object."""
        raise NotImplementedError('must be implemented in subclasses')

    def add_target_and_index(self, name_cls, sig, signode):
        modname = self.options.get(
            'module', self.env.ref_context.get('gobject:module'))
        fullname = (modname and modname + '.' or '') + name_cls[0]
        # note target
        if fullname not in self.state.document.ids:
            signode['names'].append(fullname)
            signode['ids'].append(fullname)
            signode['first'] = (not self.names)
            self.state.document.note_explicit_target(signode)
            objects = self.env.domaindata['py']['objects']
            if fullname in objects:
                self.state_machine.reporter.warning(
                    'duplicate object description of %s, ' % fullname +
                    'other instance in ' +
                    self.env.doc2path(objects[fullname][0]) +
                    ', use :noindex: for one of them',
                    line=self.lineno)
            objects[fullname] = (self.env.docname, self.objtype)

        indextext = self.get_index_text(modname, name_cls)
        if indextext:
            self.indexnode['entries'].append(('single', indextext,
                                              fullname, '', None))

    def before_content(self):
        # needed for automatic qualification of members (reset in subclasses)
        self.clsname_set = False

    def after_content(self):
        if self.clsname_set:
            self.env.ref_context.pop('gobject:class', None)
            self.env.ref_context.pop('gobject:interface', None)
            self.env.ref_context.pop('gobject:enum', None)


class PyModulelevel(PyObject):
    """
    Description of an object on module level (functions, data).
    """

    def needs_arglist(self):
        return self.objtype == 'function'

    def get_index_text(self, modname, name_cls):
        if self.objtype == 'function':
            if not modname:
                return _('%s() (built-in function)') % name_cls[0]
            return _('%s() (in module %s)') % (name_cls[0], modname)
        else:
            return ''


class PyClasslike(PyObject):
    """
    Description of a class-like object (classes, interfaces, exceptions).
    """

    def get_signature_prefix(self, sig):
        return self.objtype + ' '

    def get_index_text(self, modname, name_cls):
        if self.objtype == 'class':
            return _('%s (class in %s)') % (name_cls[0], modname)
        elif self.objtype == 'interface':
            return _('%s (interface in %s)') % (name_cls[0], modname)
        else:
            return ''

    def before_content(self):
        PyObject.before_content(self)
        if self.names:
            self.env.ref_context['gobject:%s' % self.objtype] = self.names[0][0]
            self.clsname_set = True


class PyClassmember(PyObject):
    """
    Description of a class member (methods, propertys).
    """

    def needs_arglist(self):
        return self.objtype.endswith('method') or self.objtype == 'signal'

    def get_signature_prefix(self, sig):
        if self.objtype == 'staticmethod':
            return 'static '
        elif self.objtype == 'classmethod':
            return 'static '
        elif self.objtype == 'signal':
            return 'signal '
        elif self.objtype == 'property':
            return 'property '
        return ''

    def get_index_text(self, modname, name_cls):
        name, cls = name_cls
        add_modules = self.env.config.add_module_names
        if self.objtype == 'method':
            try:
                clsname, methname = name.rsplit('.', 1)
            except ValueError:
                if modname:
                    return _('%s() (in module %s)') % (name, modname)
                else:
                    return '%s()' % name
            if modname and add_modules:
                return _('%s() (%s.%s method)') % (methname, modname, clsname)
            else:
                return _('%s() (%s method)') % (methname, clsname)
        elif self.objtype == 'staticmethod':
            try:
                clsname, methname = name.rsplit('.', 1)
            except ValueError:
                if modname:
                    return _('%s() (in module %s)') % (name, modname)
                else:
                    return '%s()' % name
            if modname and add_modules:
                return _('%s() (%s.%s static method)') % (methname, modname,
                                                          clsname)
            else:
                return _('%s() (%s static method)') % (methname, clsname)
        elif self.objtype == 'classmethod':
            try:
                clsname, methname = name.rsplit('.', 1)
            except ValueError:
                if modname:
                    return _('%s() (in module %s)') % (name, modname)
                else:
                    return '%s()' % name
            if modname:
                return _('%s() (%s.%s class method)') % (methname, modname,
                                                         clsname)
            else:
                return _('%s() (%s class method)') % (methname, clsname)
        elif self.objtype == 'property':
            try:
                clsname, propname = name.rsplit('.', 1)
            except ValueError:
                if modname:
                    return _('%s (in module %s)') % (name, modname)
                else:
                    return name
            if modname and add_modules:
                return _('%s (%s.%s property)') % (propname, modname, clsname)
            else:
                return _('%s (%s property)') % (propname, clsname)
        elif self.objtype == 'member':
            try:
                clsname, propname = name.rsplit('.', 1)
            except ValueError:
                if modname:
                    return _('%s (in module %s)') % (name, modname)
                else:
                    return name
            if modname and add_modules:
                return _('%s (%s.%s member)') % (propname, modname, clsname)
            else:
                return _('%s (%s member)') % (propname, clsname)
        elif self.objtype == 'signal':
            try:
                clsname, methname = name.rsplit('.', 1)
            except ValueError:
                if modname:
                    return _('%s() (in module %s)') % (name, modname)
                else:
                    return '%s()' % name
            if modname and add_modules:
                return _('%s() (%s.%s signal)') % (methname, modname, clsname)
            else:
                return _('%s() (%s signal)') % (methname, clsname)
        else:
            return ''

    def before_content(self):
        PyObject.before_content(self)
        lastname = self.names and self.names[-1][1]
        # FIXME: gobject:interface
        if lastname and not self.env.ref_context.get('gobject:class'):
            self.env.ref_context['gobject:class'] = lastname.strip('.')
            self.clsname_set = True


class PyModule(Directive):
    """
    Directive to mark description of a new module.
    """

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'platform': lambda x: x,
        'synopsis': lambda x: x,
        'noindex': directives.flag,
        'deprecated': directives.flag,
    }

    def run(self):
        env = self.state.document.settings.env
        modname = self.arguments[0].strip()
        noindex = 'noindex' in self.options
        env.ref_context['gobject:module'] = modname
        ret = []
        if not noindex:
            env.domaindata['py']['modules'][modname] = \
                (env.docname, self.options.get('synopsis', ''),
                 self.options.get('platform', ''), 'deprecated' in self.options)
            # make a duplicate entry in 'objects' to facilitate searching for
            # the module in PythonDomain.find_obj()
            env.domaindata['py']['objects'][modname] = (env.docname, 'module')
            targetnode = nodes.target('', '', ids=['module-' + modname],
                                      ismod=True)
            self.state.document.note_explicit_target(targetnode)
            # the platform and synopsis aren't printed; in fact, they are only
            # used in the modindex currently
            ret.append(targetnode)
            indextext = _('%s (module)') % modname
            inode = addnodes.index(entries=[('single', indextext,
                                             'module-' + modname, '', None)])
            ret.append(inode)
        return ret


class PyCurrentModule(Directive):
    """
    This directive is just to tell Sphinx that we're documenting
    stuff in module foo, but links to module foo won't lead here.
    """

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {}

    def run(self):
        env = self.state.document.settings.env
        modname = self.arguments[0].strip()
        if modname == 'None':
            env.ref_context.pop('gobject:module', None)
        else:
            env.ref_context['gobject:module'] = modname
        return []


class PyXRefRole(XRefRole):
    def process_link(self, env, refnode, has_explicit_title, title, target):
        refnode['gobject:module'] = env.ref_context.get('gobject:module')
        refnode['gobject:class'] = env.ref_context.get('gobject:class')
        if not has_explicit_title:
            title = title.lstrip('.')    # only has a meaning for the target
            target = target.lstrip('~')  # only has a meaning for the title
            # if the first character is a tilde, don't display the module/class
            # parts of the contents
            if title[0:1] == '~':
                title = title[1:]
                dot = title.rfind('.')
                if dot != -1:
                    title = title[dot + 1:]
        # if the first character is a dot, search more specific namespaces first
        # else search builtins first
        if target[0:1] == '.':
            target = target[1:]
            refnode['refspecific'] = True
        return title, target


class PythonModuleIndex(Index):
    """
    Index subclass to provide the Python module index.
    """

    name = 'modindex'
    localname = l_('Python Module Index')
    shortname = l_('modules')

    def generate(self, docnames=None):
        content = {}
        # list of prefixes to ignore
        ignores = self.domain.env.config['modindex_common_prefix']
        ignores = sorted(ignores, key=len, reverse=True)
        # list of all modules, sorted by module name
        modules = sorted(iteritems(self.domain.data['modules']),
                         key=lambda x: x[0].lower())
        # sort out collapsable modules
        prev_modname = ''
        num_toplevels = 0
        for modname, (docname, synopsis, platforms, deprecated) in modules:
            if docnames and docname not in docnames:
                continue

            for ignore in ignores:
                if modname.startswith(ignore):
                    modname = modname[len(ignore):]
                    stripped = ignore
                    break
            else:
                stripped = ''

            # we stripped the whole module name?
            if not modname:
                modname, stripped = stripped, ''

            entries = content.setdefault(modname[0].lower(), [])

            package = modname.split('.')[0]
            if package != modname:
                # it's a submodule
                if prev_modname == package:
                    # first submodule - make parent a group head
                    if entries:
                        entries[-1][1] = 1
                elif not prev_modname.startswith(package):
                    # submodule without parent in list, add dummy entry
                    entries.append([stripped + package, 1, '', '', '', '', ''])
                subtype = 2
            else:
                num_toplevels += 1
                subtype = 0

            qualifier = deprecated and _('Deprecated') or ''
            entries.append([stripped + modname, subtype, docname,
                            'module-' + stripped + modname, platforms,
                            qualifier, synopsis])
            prev_modname = modname

        # apply heuristics when to collapse modindex at page load:
        # only collapse if number of toplevel modules is larger than
        # number of submodules
        collapse = len(modules) - num_toplevels < num_toplevels

        # sort by first letter
        content = sorted(iteritems(content))

        return content, collapse


class PythonDomain(Domain):
    """Python language domain."""
    name = 'gobject'
    label = 'GObject'
    object_types = {
        'function':     ObjType(l_('function'),      'func', 'obj'),
        'class':        ObjType(l_('class'),         'class', 'exc', 'obj'),
        'interface':    ObjType(l_('interface'),     'interface', 'exc', 'obj'),
        'enum':         ObjType(l_('enum'),   'enum', 'exc', 'obj'),
        'method':       ObjType(l_('method'),        'meth', 'obj'),
        'classmethod':  ObjType(l_('class method'),  'meth', 'obj'),
        'staticmethod': ObjType(l_('static method'), 'meth', 'obj'),
        'property':     ObjType(l_('property'),      'prop', 'obj'),
        'member':       ObjType(l_('property'),      'member', 'obj'),
        'signal':       ObjType(l_('signal'),        'signal', 'obj'),
        'module':       ObjType(l_('module'),        'mod', 'obj'),
    }

    directives = {
        'function':        PyModulelevel,
        'class':           PyClasslike,
        'interface':       PyClasslike,
        'enum':            PyClasslike,
        'member':          PyClassmember,
        'method':          PyClassmember,
        'classmethod':     PyClassmember,
        'staticmethod':    PyClassmember,
        'property':        PyClassmember,
        'signal':          PyClassmember,
        'module':          PyModule,
        'currentmodule':   PyCurrentModule,
    }
    roles = {
        'exc':   PyXRefRole(),
        'func':  PyXRefRole(fix_parens=True),
        'class': PyXRefRole(),
        'interface': PyXRefRole(),
        'const': PyXRefRole(),
        'prop':  PyXRefRole(),
        'signal': PyXRefRole(fix_parens=True),
        'meth':  PyXRefRole(fix_parens=True),
        'mod':   PyXRefRole(),
        'obj':   PyXRefRole(),
        'enum':  PyXRefRole(),
        'member': PyXRefRole(),
    }
    initial_data = {
        'objects': {},  # fullname -> docname, objtype
        'modules': {},  # modname -> docname, synopsis, platform, deprecated
    }
    indices = [
        PythonModuleIndex,
    ]

    def clear_doc(self, docname):
        for fullname, (fn, _l) in list(self.data['objects'].items()):
            if fn == docname:
                del self.data['objects'][fullname]
        for modname, (fn, _x, _x, _x) in list(self.data['modules'].items()):
            if fn == docname:
                del self.data['modules'][modname]

    def merge_domaindata(self, docnames, otherdata):
        # XXX check duplicates?
        for fullname, (fn, objtype) in otherdata['objects'].items():
            if fn in docnames:
                self.data['objects'][fullname] = (fn, objtype)
        for modname, data in otherdata['modules'].items():
            if data[0] in docnames:
                self.data['modules'][modname] = data

    def find_obj(self, env, modname, classname, name, type, searchmode=0):
        """Find a Python object for "name", perhaps using the given module
        and/or classname.  Returns a list of (name, object entry) tuples.
        """
        # skip parens
        if name[-2:] == '()':
            name = name[:-2]

        if not name:
            return []

        objects = self.data['objects']
        matches = []

        newname = None
        if searchmode == 1:
            if type is None:
                objtypes = list(self.object_types)
            else:
                objtypes = self.objtypes_for_role(type)
            if objtypes is not None:
                if modname and classname:
                    fullname = modname + '.' + classname + '.' + name
                    if fullname in objects and objects[fullname][1] in objtypes:
                        newname = fullname
                if not newname:
                    if modname and modname + '.' + name in objects and \
                       objects[modname + '.' + name][1] in objtypes:
                        newname = modname + '.' + name
                    elif name in objects and objects[name][1] in objtypes:
                        newname = name
                    else:
                        # "fuzzy" searching mode
                        searchname = '.' + name
                        matches = [(oname, objects[oname]) for oname in objects
                                   if oname.endswith(searchname) and
                                   objects[oname][1] in objtypes]
        else:
            # NOTE: searching for exact match, object type is not considered
            if name in objects:
                newname = name
            elif type == 'mod':
                # only exact matches allowed for modules
                return []
            elif classname and classname + '.' + name in objects:
                newname = classname + '.' + name
            elif modname and modname + '.' + name in objects:
                newname = modname + '.' + name
            elif modname and classname and \
                    modname + '.' + classname + '.' + name in objects:
                newname = modname + '.' + classname + '.' + name
            # special case: object methods
            elif type in ('func', 'meth', 'signal', ) and '.' not in name and \
                    'object.' + name in objects:
                newname = 'object.' + name
        if newname is not None:
            matches.append((newname, objects[newname]))
        return matches

    def resolve_xref(self, env, fromdocname, builder,
                     type, target, node, contnode):
        modname = node.get('gobject:module')
        clsname = node.get('gobject:class')
        # FIXME
        searchmode = 0  # node.hasprop('refspecific') and 1 or 0
        matches = self.find_obj(env, modname, clsname, target,
                                type, searchmode)
        if not matches:
            return None
        elif len(matches) > 1:
            env.warn_node(
                'more than one target found for cross-reference '
                '%r: %s' % (target, ', '.join(match[0] for match in matches)),
                node)
        name, obj = matches[0]

        if obj[1] == 'module':
            return self._make_module_refnode(builder, fromdocname, name,
                                             contnode)
        else:
            return make_refnode(builder, fromdocname, obj[0], name,
                                contnode, name)

    def resolve_any_xref(self, env, fromdocname, builder, target,
                         node, contnode):
        modname = node.get('gobject:module')
        clsname = node.get('gobject:class')
        results = []

        # always search in "refspecific" mode with the :any: role
        matches = self.find_obj(env, modname, clsname, target, None, 1)
        for name, obj in matches:
            if obj[1] == 'module':
                results.append(('gobject:mod',
                                self._make_module_refnode(builder, fromdocname,
                                                          name, contnode)))
            else:
                results.append(('gobject:' + self.role_for_objtype(obj[1]),
                                make_refnode(builder, fromdocname, obj[0], name,
                                             contnode, name)))
        return results

    def _make_module_refnode(self, builder, fromdocname, name, contnode):
        # get additional info for modules
        docname, synopsis, platform, deprecated = self.data['modules'][name]
        title = name
        if synopsis:
            title += ': ' + synopsis
        if deprecated:
            title += _(' (deprecated)')
        if platform:
            title += ' (' + platform + ')'
        return make_refnode(builder, fromdocname, docname,
                            'module-' + name, contnode, title)

    def get_objects(self):
        for modname, info in iteritems(self.data['modules']):
            yield (modname, modname, 'module', info[0], 'module-' + modname, 0)
        for refname, (docname, type) in iteritems(self.data['objects']):
            if type != 'module':  # modules are already handled
                yield (refname, refname, type, docname, refname, 1)


def setup(app):
    app.add_domain(PythonDomain)

    return {
        'version': '0.1.0',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
