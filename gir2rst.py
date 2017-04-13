#!/usr/bin/env python3

import xmltodict
from m2r import M2R
from pprint import pprint
import re
from textwrap import indent
# from pgidocgen.pgidocgen.parser import docstring_to_rest
# from pgidocgen.pgidocgen.repo import Repository


def docstring_to_rest(docs: str) -> str:
    """Converts docstring into valid rest."""

    # This is awful and I should feel bad
    #docs = re.sub(r'^(\s*)## (.*)$', r'\1**\2**', docs, flags=re.M)
    docs = re.sub(r'(^|\s|-)%([A-Z_0-9]+)\b', r'\1:c:macro:`\2`', docs)
    docs = re.sub(r'(^|\s)#(\w+)\b', r'\1:class:`\2`', docs)
    docs = re.sub(r'(^|\s)@(\w+)\b', r'\1:c:data:`\2`', docs)
    docs = re.sub(r'\b([A-Z_]+\(\))', r':c:macro:`\1`', docs)
    docs = re.sub(r'([^`]|\b)([A-Za-z0-9_]+\(\))', r'\1:c:func:`\2`', docs)

    # Code snippets
    code = re.findall(r'\|\[.*$\n([^\]]+)', docs, flags=re.M)
    for c in code:
        docs = docs.replace(c, indent(c, '  '))
    docs = re.sub(
        r'( *)\|\[(?:<!-- language="(?P<language>\w+)" -->)?(?P<body>(?:(?:.|\n)(?!\]\|))+)\s?\]\|',
        r'\n\1.. code-block:: \g<language>\n\g<body>', docs)  # FIXME

    #docs = re.sub(
    #    r'( *)\|\[(?:<!-- language="(?:\w+)" -->)?(?P<body>(?:(?:.|\n)(?!\]\|))+)\s?\]\|',
    #    r'\n\1::\n\g<body>', docs)  # FIXME

    # Handle remaining markdown
    return M2R().parse(docs).strip()


class RstDoc:
    def __init__(self, name: str):
        self._f = open('test/' + name + '.rst', 'w')

    def write(self, text: str='', indent: int=0, newlines=1):
        for line in text.split('\n'):
            if line:
                if indent:
                    self._f.write('  ' * indent)
                self._f.write(line)
            self._f.write('\n')
        self._f.write('\n' * newlines)

    def directive(self, directive: str, value: str='', indent=0):
        self.write('.. {}:: {}'.format(directive, value), indent=indent)

    def header(self, text: str):
        self.write('{0}\n{1}\n{0}'.format('#' * len(text), text))

    def option(self, option: str, value: str, indent: int=0):
        value = docstring_to_rest(' '.join(v.strip() for v in value.split('\n')))
        self.write('{}:{}: {}'.format('  ' * indent, option, value), newlines=0)

    def write_function(self, func: dict, prefix: str, func_type: str):
        if '@moved-to' in func:
            return  # For now..
        if not func.get('@introspectable', True):
            return
        indent = 0 if func_type == 'function' else 1
        content_indent = indent + 1

        def flatten_params(params):
            ret = []
            for _, param in params.items():
                if isinstance(param, list):
                    ret += param
                else:
                    ret.append(param)
            return ret

        def get_type_name(d: dict) -> str:
            # TODO: Handle containers
            type_ = d.get('type', {}).get('@name', '')

            # It might be a class within the same namespace
            if type_ and type_[0].isupper() and '.' not in type_:
                namespace = prefix.partition('.')[0]
                type_ = '{}.{}'.format(namespace, type_)

            return type_

        parameters = flatten_params(func.get('parameters', {}))
        param_names = (param['@name'] for param in parameters)
        full_name = '{}.{}({})'.format(prefix, func['@name'], ', '.join(param_names))

        self.directive(func_type, full_name, indent=indent)

        docs = func.get('doc', {}).get('#text', '')
        if docs:
            docs = docstring_to_rest(docs)
            self.write(docs, indent=content_indent)

        for parameter in parameters:
            # TODO: More attributes
            if 'doc' in parameter:
                doc = docstring_to_rest(parameter['doc']['#text'])
                self.option('param ' + parameter['@name'], doc, indent=content_indent)
            if 'type' in parameter:
                type_ = get_type_name(parameter)
                self.option('type ' + parameter['@name'], ':class:`{}`'.format(type_),
                            indent=content_indent)

        return_ = func.get('return-value', {})
        return_text = return_.get('doc', {}).get('#text', '')
        return_type = get_type_name(return_)
        if return_text:
            self.option('returns', return_text, indent=content_indent)
        if return_type and return_type != 'none':
            self.option('rtype', ':class:`{}`'.format(return_type), indent=content_indent)
        self.write(newlines=0)


def get_list(d: dict, name: str) -> list:
    r = d.get(name, [])
    if not isinstance(r, list):
        r = [r]
    return r

if __name__ == '__main__':
    f = open('/usr/share/gir-1.0/Gio-2.0.gir', 'rb')
    # TODO: Perhaps drop the dependency
    namespace = xmltodict.parse(f)['repository']['namespace']
    name = namespace['@name']
    version = namespace['@version']
    full_name = '{}-{}'.format(name, version)

    doc = RstDoc(full_name)

    doc.directive('default-domain', 'gobject')
    doc.write()
    doc.header(full_name)
    doc.write()

    for key in namespace.keys(): print(key)

    for class_ in get_list(namespace, 'class'):
        if not class_.get('@introspectable', True):
            continue
        class_name = class_['@name']
        doc.directive('class', '{}.{}'.format(name, class_name))
        docs = class_.get('doc', {}).get('#text', '')
        if doc:
            doc.write(docstring_to_rest(docs), indent=1)

        #for key in class_.keys(): print(key)
        # pprint(class_)
        # print()

        for func in get_list(class_, 'function') + get_list(class_, 'constructor'):
            doc.write_function(func, '{}.{}'.format(name, class_name), 'classmethod')

        for meth in get_list(class_, 'method'):
            doc.write_function(meth, '{}.{}'.format(name, class_name), 'method')

        for prop in get_list(class_, 'property'):
            doc.directive('property', '{}.{}.{}'.format(name, class_name, prop['@name']), indent=1)
            docs = prop.get('doc', {}).get('#text', '')
            if docs:
                docs = docstring_to_rest(docs)
                doc.write(docs, indent=1)

        for signal in get_list(class_, 'glib:signal'):
            doc.write_function(signal, '{}.{}'.format(name, class_name), 'signal')

    for func in get_list(namespace, 'function'):
        doc.write_function(func, name, 'function')

    for enum in get_list(namespace, 'enumeration'):
        enum_name = '{}.{}'.format(name, enum['@name'])
        doc.directive('enum', enum_name)
        docs = enum.get('doc', {}).get('#text', '')
        if doc:
            doc.write(docstring_to_rest(docs), indent=1)
        for member in get_list(enum, 'member'):
            # FIXME: C identifier to Gir style
            identifier = '{}.{} = {}'.format(enum_name, member['@c:identifier'],
                                             member['@value'])
            doc.directive('member', identifier, indent=1)
            docs = member.get('doc', {}).get('#text', '')
            if doc:
                doc.write(docstring_to_rest(docs), indent=2)
        pprint(enum)
