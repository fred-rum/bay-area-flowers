# My files
from files import *

def strip_comments(to_filename, from_filename=None, code=None):
    def repl_string_or_comment(matchobj):
        string = matchobj.group(1)
        comment = matchobj.group(2)

        if string is not None:
            return string
        elif 'Copyright Chris Nelson' in comment:
            return comment
        else:
            return ''

    if not from_filename:
        from_filename = to_filename

    is_js = (to_filename.endswith('.js'))

    with open(f'{root_path}/src/{from_filename}', mode='r', encoding='utf-8') as r:
        txt = r.read()

    if code:
        txt = re.sub(r'/\* insert code here \*/', code, txt)

    # Match either a complete quoted string (which is returned unchanged) or
    # whitespace followed by a comment (which is removed).
    #
    # If a string contains what appears to be a comment, the string is matched
    # because it starts first.  And vice versa for a comment that contains
    # quotation marks.
    #
    # Note that a Javascript regex (surrounded by slashes) could include
    # a quotation mark and/or something that looks like the start of a comment,
    # but it's impossible to reliably detect a regex without a full Javascript
    # parser.  So we exclude an escaped quotation mark to start a string (in
    # case that appears in a regex) and otherwise hope for the best.
    quote1 = r'(?<!\\)"(?:[^"\\]|\\.)*"'
    quote2 = r"(?<!\\)'(?:[^'\\]|\\.)*'"
    comment = r'/\s+?$|\s*/\*.*?\*/'
    if is_js:
        comment += r'|\s*//[^\r\n]*$'

        # If the -debug arg is given, keep console debug statements.
        # Otherwise, delete them.
        if not arg('-debug'):
            comment += r'|\s*console\.(error|warn|info|log)\([^\r\n]*\);\s*$'

    pattern = fr'({quote1}|{quote2})|({comment})'
    txt = re.sub(pattern, repl_string_or_comment, txt,
                 flags=re.DOTALL|re.MULTILINE)
    # Collapse blank lines and whitespace at the end of lines.
    txt = re.sub(r'\s+\n', '\n', txt)

    with open(f'{root_path}/{to_filename}', mode='w', encoding='utf-8') as w:
        w.write(txt)
