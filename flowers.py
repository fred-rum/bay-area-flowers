#!/cygdrive/c/Python27/python.exe c:/Users/Chris/Documents/GitHub/bay-area-flowers/flowers.py

# Run as:
# /cygdrive/c/Users/Chris/Documents/GitHub/bay-area-flowers/flowers.py

# terminology (e.g. for variable names):
# page - a flower or container HTML page, and the info associated with it
# txt - the text that defines the contents of a page, often from a .txt file
# jpg - a photo; a page can include multiple photos (or none)
#
# flower - a flower.
#          Some flowers don't have an associated page,
#          and container pages don't have a (specific) associated flower.
#
# name - the name of a page and/or flower, or of an associated txt file
#        and/or jpg files
#        (i.e. ignorning the filename extension and the "-#" jpg number).
#        a flower uses its common name (not scientific name).
#
# color - a flower color.
#
# The variable name for a dictionary is constructed as
# {what it's for}_{what it holds}.
# E.g. page_parent holds the parent info for a page.
#
# In many cases, a dictionary does not necessarily contain data for every key.
# So when it is accessed, we must first check whether the key exists in the
# dictionary before getting its contents.


import os
import shutil
import filecmp
import subprocess
import re
import csv
import cStringIO
import yaml
import codecs


root = 'c:/Users/Chris/Documents/GitHub/bay-area-flowers'

# Keep a copy of the previous html files so that we can
# compare differences after creating the new html files.
shutil.rmtree(root + '/prev', ignore_errors=True)

# Apparently Windows sometimes lets the call complete when the
# remove is not actually done yet, and then the rename fails.
# In that case, keep retrying the rename until it succeeds.
done = False
while not done:
    try:
        os.rename(root + '/html', root + '/prev')
        done = True
    except WindowsError as error:
        pass

os.mkdir(root + '/html')

# key: page name
page_parent = {} # a set of names of the page's parent pages
page_child = {} # a list of names of the page's child pages
page_txt = {} # txt (string) (potentially with some parsing done to it)

# A set of color names that the page is linked from.
# (Initially this is just the flower colors,
# but container pages get added later.)
page_color = {}

page_default = set() # indicates whether a page is "default" (no added text)

page_com = {} # common name
page_sci = {} # scientific name
page_obs = {} # number of observations
page_obs_rg = {} # number of observations that are research grade
page_taxon_id = {} # iNaturalist taxon ID
page_parks = {} # for each page, stores a dictionary of park_name : count

sci_page = {} # scientific name -> page name
genus_page_list = {} # genus -> list of page names
genus_set = set() # set of genuses with a container page

# Define a list of supported colors.
color_list = ['blue',
              #'blue purple',
              'purple',
              'red purple',
              'red',
              'orange',
              'yellow',
              'white',
              'pale blue',
              'pale purple',
              'pink',
              'salmon',
              'cream',
              'other']

# key: color
# value: page list
color_page_list = {}

# A few functions need a small horizontal spacer,
# so we define a common one here.
horiz_spacer = '<div class="horiz-space"></div>'

# Read miscellaneous flower info from the YAML file.
with open(root + '/color.yaml') as f:
    yaml_data = yaml.safe_load(f)
for page in yaml_data:
    page_color[page] = set([x.strip() for x in yaml_data[page].split(',')])
    for color in page_color[page]:
        if color not in color_list:
            print 'page {page} uses undefined color {color}'.format(page=page, color=color)

# Read the mapping of iNaturalist observation locations to short park names.
park_map = {}
with codecs.open(root + '/parks.yaml', mode='r', encoding="utf-8") as f:
    yaml_data = yaml.safe_load(f)
for x in yaml_data:
    if isinstance(x, basestring):
        park_map[x] = x
    else:
        for y in x:
            park_map[x[y]] = y

# Get a list of files with the expected suffix in the designated directory.
def get_file_list(subdir, ext):
    file_list = os.listdir(root + '/' + subdir)
    base_list = []
    for filename in file_list:
        pos = filename.rfind(os.extsep)
        if pos > 0:
            file_ext = filename[pos+len(os.extsep):].lower()
            if file_ext == ext:
                base = filename[:pos]
                base_list.append(base)
    return base_list

page_list = get_file_list('txt', 'txt')
jpg_list = get_file_list('photos', 'jpg')
thumb_list = get_file_list('thumbs', 'jpg')

def get_page_from_jpg(jpg):
    page = re.sub(r',([-0-9]*)$', r'', jpg)

    # Remove ssp. and other elaborations that I use in my keywords
    # but not in my page names.
    page = re.sub(r' ssp. | spp. ', ' ', page)

    return page

def get_com(page):
    if page in page_com:
        return page_com[page]
    else:
        return page

def get_elab(sci):
    matchobj = re.match(r'([^ ]+ [^ ]+) ([^ ]+)$', sci)
    if ' ' not in sci:
        # one word in the scientific name implies a genus.
        return '{genus} spp.'.format(genus=sci)
    elif matchobj:
        # three words in the scientific name implies a subspecies
        # (or variant, or whatever).  Default to "ssp."
        return '{species} ssp. {ssp}'.format(species=matchobj.group(1),
                                             ssp=matchobj.group(2))
    else:
        return sci

def get_full(page, lines=2):
    com = get_com(page)
    if page in page_sci:
        sci = page_sci[page]
        elab = get_elab(sci)
        if com == sci:
            return "<i>{elab}</i>".format(elab=elab)
        elif lines == 2:
            return "{com}<br/><i>{elab}</i>".format(com=com, elab=elab)
        else: # lines == 1
            return "{com} (<i>{elab}</i>)".format(com=com, elab=elab)
    else:
        return com

flower_jpg_list = {}
for jpg in sorted(jpg_list):
    flower = get_page_from_jpg(jpg)
    if flower not in flower_jpg_list:
        flower_jpg_list[flower] = []
    flower_jpg_list[flower].append(jpg)

# Compare the photos directory with the thumbs directory.
# If a file exists in photos and not thumbs, create it.
# If a file is newer in photos than in thumbs, re-create it.
# If a file exists in thumbs and not photos, delete it.
# If a file is newer in thumbs than in photos, leave it unchanged.
for name in thumb_list:
    if name not in jpg_list:
        thumb_file = root + '/thumbs/' + name + '.jpg'
        os.remove(thumb_file)

mod_list = []
for name in jpg_list:
    photo_file = root + '/photos/' + name + '.jpg'
    thumb_file = root + '/thumbs/' + name + '.jpg'
    if (name not in thumb_list or
        os.path.getmtime(photo_file) > os.path.getmtime(thumb_file)):
        mod_list.append(photo_file)

if mod_list:
    with open(root + "/convert.txt", "w") as w:
        for filename in mod_list:
            filename = re.sub(r'/', r'\\', filename)
            w.write(filename + '\n')
    root_mod = re.sub(r'/', r'\\', root)
    cmd = ['C:/Program Files (x86)/IrfanView/i_view32.exe',
           '/filelist={root}\\convert.txt'.format(root=root_mod),
           '/aspectratio',
           '/resize_long=200',
           '/resample',
           '/jpgq=80',
           '/convert={root}\\thumbs\\*.jpg'.format(root=root_mod)]
    subprocess.Popen(cmd).wait()

# Check if check_page is an ancestor of cur_page (for loop checking).
def is_ancestor(cur_page, check_page):
    if cur_page == check_page:
        return True

    if cur_page in page_parent:
        for parent in page_parent[cur_page]:
            if is_ancestor(parent, check_page):
                return True

    return False

def assign_child(parent, child):
    if is_ancestor(parent, child):
        print "circular loop when creating link from {parent} to {child}".format(parent=parent, child=child)
    else:
        if child not in page_parent:
            page_parent[child] = set()
        page_parent[child].add(parent)

        if parent not in page_child:
            page_child[parent] = []
        page_child[parent].append(child)

# Read txt files, but perform limited substitutions for now.
# More will be done once we have a complete set of parent->child relationships.
def read_txt(page):
    with open(root + "/txt/" + page + ".txt", "r") as r:
        s = r.read()

    # Replace a {child:[page]} link with just {[page]} and record the
    # parent->child relationship.
    # Define the re.sub replacement function inside the calling function
    # so that it has access to the calling context.
    def repl_child(matchobj):
        x = matchobj.group(1)
        child = matchobj.group(2)
        suffix = matchobj.group(3)
        if not suffix:
            suffix = ''
        assign_child(page, child)
        if x == '+':
            return '{' + child + ':' + child + suffix + '.jpg} {' + child + '}'
        else:
            return '{' + child + '}'

    def repl_sci(matchobj):
        sci = matchobj.group(1)
        page_sci[page] = sci
        sci_page[sci] = page
        return ''

    def repl_com(matchobj):
        page_com[page] = matchobj.group(1)
        return ''

    s = re.sub(r'{(child:|\+)([^},]+)(,[-0-9]*)?}', repl_child, s)
    s = re.sub(r'{sci:(.*)}\n', repl_sci, s)
    s = re.sub(r'{com:(.*)}\n', repl_com, s)
    page_txt[page] = s

def create_link(page, lines):
    if page in page_child:
        style = ' class="parent"'
    else:
        style = ' class="leaf"'
    return '<a href="{page}.html"{style}>{full}</a>'.format(page=page, style=style, full=get_full(page, lines))


# For containers, sum the observation counts of all children,
# *but* if a flower is found via multiple paths, count it only once.
# Two values are returned: (n, rg)
#   n is the observation count
#   rg is the research-grade observation count (0 <= rg <= n)
def count_matching_obs(page, color, match_flowers):
    if page in match_flowers: return (0, 0)

    n = 0
    rg = 0

    # If a container page contains exactly one descendant with a matching
    # color, the container isn't listed on the color page, and the color
    # isn't listed in page_color for the page.  Therefore, we follow all
    # child links blindly and only compare the color when we reach a flower
    # with an observation count.
    if page in page_obs and page_matches_color(page, color):
        n += page_obs[page]
        rg += page_obs_rg[page]
        match_flowers.add(page)

    if page in page_child:
        for child in page_child[page]:
            (ch_n, ch_rg) = count_matching_obs(child, color, match_flowers)
            n += ch_n
            rg += ch_rg

    return (n, rg)

# Write the iNaturalist observation count (including all children).
def write_obs(w, page):
    (n, rg) = count_matching_obs(page, None, set())

    if n == 0 and page not in page_sci:
        return

    if page in page_taxon_id:
        link = 'https://www.inaturalist.org/observations/chris_nelson?taxon_id={taxon_id}&order_by=observed_on'.format(taxon_id=page_taxon_id[page])
    elif page in page_sci:
        link = 'https://www.inaturalist.org/observations/chris_nelson?search_on=names&q={sci}&order_by=observed_on'.format(sci=page_sci[page])
    else:
        link = None

    w.write('<p/>\n')

    if link:
        w.write('<a href="{link}" target="_blank">Chris&rsquo;s observations</a>: '.format(link=link))
    else:
        w.write('Chris&rsquo;s observations: ')

    if page in page_sci and page_sci[page].count(' ') == 1:
        rg_txt = 'research grade'
    else:
        rg_txt = 'research grade to species level'

    if n == 0:
        w.write('none')
    elif rg == 0:
        w.write('{n} (none are {rg_txt})'.format(n=n, rg_txt=rg_txt))
    elif rg == n:
        if n == 1:
            w.write('1 ({rg_txt})'.format(rg_txt=rg_txt))
        else:
            w.write('{n} (all are {rg_txt})'.format(n=n, rg_txt=rg_txt))
    else:
        w.write('{n} ({rg} are {rg_txt})'.format(n=n, rg=rg, rg_txt=rg_txt))


    if page not in page_child and page in page_parks:
        w.write('''
<span class="toggle-details" onclick="fn_details(this)">[show details]</span><p/>
<div id="details">
Locations:
<ul>
''')
        for park in sorted(page_parks[page], key = lambda x: page_parks[page][x], reverse=True):
            html_park = park.encode('ascii', 'xmlcharrefreplace')
            count = page_parks[page][park]
            if count == 1:
                w.write('<li>{park}</li>\n'.format(park=html_park))
            else:
                w.write('<li>{park}: {count}</li>\n'.format(park=html_park, count=count))
        w.write('</ul></div>\n')
    else:
        w.write('<p/>\n')

def write_external_links(w, page):
    sci = page_sci[page]
    if ' ' in sci:
        elab = get_elab(sci)
    else:
        # A one-word genus should be sent as is, not as '[genus] spp.'
        elab = sci

    w.write('<p/>')

    if page in page_taxon_id:
        w.write('<a href="https://www.inaturalist.org/taxa/{taxon_id}">iNaturalist</a> &ndash;\n'.format(taxon_id=page_taxon_id[page]))

    w.write('<a href="https://www.calflora.org/cgi-bin/specieslist.cgi?namesoup={elab}" target="_blank">CalFlora</a> &ndash;\n'.format(elab=elab));

    if ' ' in sci:
        # CalPhotos cannot be searched by genus only.
        w.write('<a href="https://calphotos.berkeley.edu/cgi/img_query?where-taxon={elab}" target="_blank">CalPhotos</a> &ndash;\n'.format(elab=elab));

    # Jepson uses "subsp." instead of "ssp.", but it also allows us to
    # search with that qualifier left out entirely.
    w.write('<a href="http://ucjeps.berkeley.edu/eflora/search_eflora.php?name={sci}" target="_blank">Jepson eFlora</a><p/>\n'.format(sci=sci));

def write_parents(w, page):
    w.write('Pages that link to this one:<p/>\n')
    w.write('<ul/>\n')

    if page in page_parent:
        for parent in sorted(page_parent[page]):
            w.write('<li>{link}</li>\n'.format(link=create_link(parent, 1)))

    if page in page_color:
        for color in color_list:
            if color in page_color[page]:
                w.write('<li><a href="{color}.html">{color} flowers</a></li>\n'.format(color=color))

    w.write('<li><a href="all.html">all flowers</a></li>\n')
    w.write('</ul>\n')

def write_header(w, title, h1):
    w.write('''<!-- Copyright 2019 Chris Nelson - All rights reserved. -->
<html lang="en">
<head>
<meta http-equiv="content-type" content="text/html; charset=UTF-8">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>{title}</title>
<link rel="shortcut icon" href="../favicon/favicon.ico">
<link rel="icon" sizes="16x16 32x32 64x64" href="../favicon/favicon.ico">
<link rel="icon" type="image/png" sizes="192x192" href="../favicon/favicon-192.png">
<link rel="icon" type="image/png" sizes="160x160" href="../favicon/favicon-160.png">
<link rel="icon" type="image/png" sizes="96x96" href="../favicon/favicon-96.png">
<link rel="icon" type="image/png" sizes="64x64" href="../favicon/favicon-64.png">
<link rel="icon" type="image/png" sizes="32x32" href="../favicon/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="../favicon/favicon-16.png">
<link rel="apple-touch-icon" href="../favicon/favicon-57.png">
<link rel="apple-touch-icon" sizes="114x114" href="../favicon/favicon-114.png">
<link rel="apple-touch-icon" sizes="72x72" href="../favicon/favicon-72.png">
<link rel="apple-touch-icon" sizes="144x144" href="../favicon/favicon-144.png">
<link rel="apple-touch-icon" sizes="60x60" href="../favicon/favicon-60.png">
<link rel="apple-touch-icon" sizes="120x120" href="../favicon/favicon-120.png">
<link rel="apple-touch-icon" sizes="76x76" href="../favicon/favicon-76.png">
<link rel="apple-touch-icon" sizes="152x152" href="../favicon/favicon-152.png">
<link rel="apple-touch-icon" sizes="180x180" href="../favicon/favicon-180.png">
<meta name="msapplication-TileColor" content="#FFFFFF">
<meta name="msapplication-TileImage" content="../favicon/favicon-144.png">
<meta name="msapplication-config" content="../favicon/browserconfig.xml">
<link rel="stylesheet" href="../bafg.css">
</head>
<body>
<div id="search-container">
<input type="text" id="search" spellcheck="false" placeholder="search for a flower...">
<div id="autocomplete-box"></div>
</div>
<div id="body">
<h1 id="title">{h1}</h1>
'''.format(title=title, h1=h1))

def write_footer(w):
    w.write('''
<hr/>
<a href="../index.html">BAFG</a> <span class="copyright">&ndash; Copyright 2019 Chris Nelson</span>
</div>
<script src="../pages.js"></script>
<script src="../search.js"></script>
</body>
''')

###############################################################################
# The giant 'parse' function, which turns txt into html
# and writes the resulting file.

repl_easy_dict = {
    # Replace HTTP links in the text with ones that open a new tab.
    # (Presumably they're external links or they'd be in {...} format.)
    '<a href=' : '<a target="_blank" href=',

    # Replace {default} with all the default fields.
    '{default}' : '{jpgs}\n',

    # Handle boxes on key pages.
    '{[' : '<div class="box">',
    ']}' : '</div>',

    # Replace common Jepson codes.
    '+-' : '&plusmn;',
    '--' : '&ndash;',
    '<=' : '&le;',
    '>=' : '&ge;',
    '<<' : '&#8810',
    '>>' : '&#8811',

    # '<' and '>' should be escaped, but for now I'll leave them alone
    # because the browser seems to figure them out correctly, and it's
    # probably smarter about it than I would be.
}

repl_easy_regex = re.compile('({ex})'.format(ex='|'.join(map(re.escape, repl_easy_dict.keys()))))

def parse(page, s):
    def repl_easy(matchobj):
        return repl_easy_dict[matchobj.group(1)]

    # replace the easy (fixed-value) stuff.
    s = repl_easy_regex.sub(repl_easy, s)

    def repl_list(matchobj):
        c = matchobj.group(1)
        c = re.sub(r'\n', r'</li>\n<li>', c)

        # If there's a sublist, it's <ul> and </ul> must be on their own lines,
        # in which case we remove the accidental surrounding <li>...</li>.
        c = re.sub(r'<li>(<(/?)ul>)</li>', r'\1', c)

        return '\n<ul>\n<li>{c}</li>\n</ul>\n'.format(c=c)

    s = re.sub(r'\n{-\n(.*?)\n-}\n', repl_list, s, flags=re.DOTALL)

    # Replace {jpgs} with all jpgs that exist for the flower.
    def repl_jpgs(matchobj):
        if page in flower_jpg_list:
            jpgs = ['{{{jpg}.jpg}}'.format(jpg=jpg) for jpg in flower_jpg_list[page]]
            return ' '.join(jpgs)
        else:
            return '{no photos.jpg}'

    s = re.sub(r'{jpgs}', repl_jpgs, s)

    # Look for any number of {photos} followed by all text up to the
    # first \n\n or \n+EOF.  Photos can be my own or CalPhotos.
    # The photos and text are grouped together and vertically centered.
    # The text is also put in a <span> for correct whitespacing.
    def repl_photo_box(matchobj):
        imgs = matchobj.group(1)
        text = matchobj.group(2)

        # If the text after the images appears to be a species link followed
        # by more text, then duplicate and contain the species link so that
        # the following text can either be in the same column or on a different
        # row, depending on the width of the viewport.
        matchobj2 = re.match(r'({.*}\s*)\n(.*)', text, flags=re.DOTALL)
        if matchobj2:
            species = matchobj2.group(1)
            text = matchobj2.group(2)
            # [div-flex-horiz-or-vert
            #  [div-horiz photos, (narrow-only) species]
            #  [span-vert (wide-only) species, text]
            # ]
            return '<div class="flex-width"><div class="photo-box">{imgs}<span class="show-narrow">{species}</span></div><span><span class="show-wide">{species}</span>{text}</span></div>'.format(imgs=imgs, species=species, text=text)
        else:
            return '<div class="photo-box">{imgs}<span>{text}</span></div>'.format(imgs=imgs, text=text)

    s = re.sub(r'((?:\{(?:jpgs|[^\}]+.jpg|https://calphotos.berkeley.edu/[^\}]+)\} *(?=\s)?)+)(.*?)(?=\n(\n|\Z))', repl_photo_box, s, flags=re.DOTALL)

    # Replace a pair of newlines with a paragraph separator.
    # (Do this after making specific replacements based on paragraphs,
    # but before replacements that might create empty lines.)
    s = s.replace('\n\n', '\n<p/>\n')

    # Replace {*.jpg} with a thumbnail image and a link to the full-sized image.
    def repl_jpg(matchobj):
        jpg = matchobj.group(1)

        # Decompose a jpg reference of the form {[page]:[img].jpg}
        pos = jpg.find(':')
        if pos > 0:
            link = jpg[:pos]
            jpg = jpg[pos+1:]
            link_to_jpg = False
        else:
            link_to_jpg = True

        jpg_page = page
        while jpg not in jpg_list:
            # If the "jpg" name is actually a flower name,
            # use the first jpg of that flower.
            if jpg in flower_jpg_list:
                jpg = flower_jpg_list[jpg][0]
                break

            # If the "jpg" name is actually a parent page name,
            # drill into its first child and try again.
            if jpg in page_child:
                jpg = page_child[jpg][0]
                continue
            else:
                break

        thumb = '../thumbs/{jpg}.jpg'.format(jpg=jpg)

        if link_to_jpg:
            href = '../photos/{jpg}.jpg'.format(jpg=jpg)
        else:
            href = '{link}.html'.format(link=link)

        if jpg in jpg_list:
            if page in page_child:
                img_class = 'page-thumb'
            else:
                img_class = 'leaf-thumb'
            img = '<a href="{href}"><img src="{thumb}" width="200" height="200" class="{img_class}"></a>'.format(href=href, thumb=thumb, img_class=img_class)
        else:
            img = '<a href="{href}" class="missing"><div class="page-thumb-text"><span>{jpg}</span></div></a>'.format(jpg=jpg, href=href)
            print '{jpg}.jpg missing'.format(jpg=jpg)

        return img + horiz_spacer

    s = re.sub(r'{([^}]+).jpg}', repl_jpg, s)

    # Replace a {CalPhotos:text} reference with a 200px box with
    # "CalPhotos: text" in it.
    # The entire box is a link to CalPhotos.
    # The ":text" part is optional.
    def repl_calphotos(matchobj):
        href = matchobj.group(1)
        pos = href.find(':') # find the colon in "http:"
        pos = href.find(':', pos+1) # find the next colon, if any
        if pos > 0:
            text = '<br/>' + href[pos+1:]
            href = href[:pos]
        else:
            text = ''

        img = '<a href="{href}" target="_blank" class="enclosed"><div class="page-thumb-text"><span><span style="text-decoration:underline;">CalPhotos</span>{text}</span></div></a>'.format(href=href, text=text)

        return img + horiz_spacer

    s = re.sub(r'\{(https://calphotos.berkeley.edu/[^\}]+)\}', repl_calphotos, s)

    # Replace a {[common]:[scientific]} reference with a link to CalFlora.
    def repl_calflora(matchobj):
        com = matchobj.group(1)
        elab = matchobj.group(2)
        if com and com[0] == '-':
            com = com[1:]
            lines = 1
        else:
            lines = 2
        if com:
            if lines == 1:
                text = '{com} (<i>{elab}</i>)'.format(com=com, elab=elab)
            else:
                text = '{com}<br/><i>{elab}</i>'.format(com=com, elab=elab)
        else:
            text = '<i>{elab}</i>'.format(elab=elab)
        return '<a href="https://www.calflora.org/cgi-bin/specieslist.cgi?namesoup={elab}" target="_blank" class="external">{text}</a>'.format(elab=elab, text=text)

    s = re.sub(r'{([^\}]*):([^\}]+)}', repl_calflora, s)

    # Any remaining {reference} should refer to another page.
    # Replace it with a link to one of my pages if I can,
    # or otherwise to CalFlora if it is a scientific species name,
    # or otherwise leave it unchanged.
    def repl_link(matchobj):
        link = matchobj.group(1)
        if link[0] == '-':
            link = link[1:]
            lines = 1
        else:
            lines = 2
        if link in page_list:
            return create_link(link, lines)
        else:
            print 'Broken link {link} on page {page}'.format(link=link, page=page)
            return '{' + link + '}'

    s = re.sub(r'{([^}]+)}', repl_link, s)

    with open(root + "/html/" + page + ".html", "w") as w:
        com = get_com(page)

        # If the page's common name is the same as its scientific name,
        # then the h1 header should be italicized and elaborated.
        if page in page_sci and page_sci[page] == com:
            h1 = '<i>{elab}</i>'.format(elab=get_elab(com))
        else:
            h1 = com

        write_header(w, com, h1)

        if h1 == com and page in page_sci:
            # We printed the common name (not the italicized scientific name)
            # in the h1 header, and we have a scientific name.
            w.write('<b><i>{elab}</i></b><p/>\n'.format(elab=get_elab(page_sci[page])))

        w.write(s)
        write_obs(w, page)
        if page in page_sci:
            write_external_links(w, page)
        w.write('<hr/>\n')
        write_parents(w, page)
        write_footer(w)

    if page not in page_child and page not in page_color:
        print 'No color for {page}'.format(page=page)

    # record all pages that are within each genus
    if page in page_sci:
        sci = page_sci[page]
        pos = sci.find(' ')
        if pos > -1:
            genus = sci[:pos]
            if genus not in genus_page_list:
                genus_page_list[genus] = []
            genus_page_list[genus].append(page)
        else:
            genus_set.add(sci)

###############################################################################

# Read the txt files and record names and parent->child relationships.
for page in page_list:
    read_txt(page)

# Create txt for all unassociated jpgs.
for name in sorted(jpg_list):
    page = get_page_from_jpg(name)
    if page not in page_list:
        page_list.append(page)
        page_txt[page] = '{default}'
        page_default.add(page)

def unicode_csv_reader(unicode_csv_data, dialect=csv.excel, **kwargs):
    # csv.py doesn't do Unicode; encode temporarily as UTF-8:
    csv_reader = csv.reader(utf_8_encoder(unicode_csv_data),
                            dialect=dialect, **kwargs)
    for row in csv_reader:
        # decode UTF-8 back to Unicode, cell by cell:
        yield [unicode(cell, 'utf-8') for cell in row]

def utf_8_encoder(unicode_csv_data):
    for line in unicode_csv_data:
        yield line.encode('utf-8')

# Read my observations file (exported from iNaturalist) and use it as follows:
#   Associate common names with scientific names
#   Get a count of observations (total and research grade) of each flower.
#   Get an iNaturalist taxon ID for each flower.
with codecs.open(root + '/observations.csv', mode='r', encoding="utf-8") as f:
    csv_reader = unicode_csv_reader(f)
    header_row = csv_reader.next()

    com_idx = header_row.index('common_name')
    sci_idx = header_row.index('scientific_name')
    rg_idx = header_row.index('quality_grade')
    taxon_idx = header_row.index('taxon_id')
    place_idx = header_row.index('place_guess')
    private_place_idx = header_row.index('private_place_guess')

    park_nf_list = set()

    for row in csv_reader:
        sci = row[sci_idx]

        # In the highly unusual case of no scientific name for an observation,
        # just throw it out.
        if not sci: continue

        # The common name is forced to all lower case to match my convention.
        # The scientific name is left in its standard case.
        com = row[com_idx].lower()
        taxon_id = row[taxon_idx]
        rg = row[rg_idx]

        park = row[private_place_idx]
        if not park:
            park = row[place_idx]

        for x in park_map:
            if x in park:
                short_park = park_map[x]
                break
        else:
            park_nf_list.add(park)
            short_park = park

        if sci in sci_page:
            page = sci_page[sci]
        else:
            # We record observations even if we don't have a page for them
            # so that we can identify missing pages at the end.
            # If there is a page for the scientific name, use it.
            # Otherwise, prefer the common name if we have it.
            if sci in page_txt or not com:
                page = sci
            else:
                page = com
            page_sci[page] = sci
            sci_page[sci] = page

        if page not in page_obs:
            page_obs[page] = 0
            page_obs_rg[page] = 0
            page_parks[page] = {}
        page_obs[page] += 1
        if rg == 'research':
            page_obs_rg[page] += 1
        page_taxon_id[page] = taxon_id
        if short_park not in page_parks[page]:
            page_parks[page][short_park] = 1
        else:
            page_parks[page][short_park] += 1

if park_nf_list:
    print "Parks not found:"
    for x in park_nf_list:
        print "  " + repr(x)

for page in page_list:
    if page not in page_sci and page[0].isupper():
        # The page name looks like a scientific name, which the page doesn't
        # have yet, so make it happen.
        page_sci[page] = page
        sci_page[page] = page

# Get a list of pages without parents (top-level pages).
top_list = [x for x in page_list if x not in page_parent]

def page_matches_color(page, color):
    return (color == None or
            (page in page_color and color in page_color[page]) or
            (page not in page_color and color == 'other'))

# Find all flowers that match the specified color.
# Also find all pages that include *multiple* child pages that match.
# If a parent includes multiple matching child pages, those child pages are
# listed only under the parent and not individually.
# If a parent includes only one matching child page, that child page is
# listed individually, and the parent is not listed.
#
# If color == None, every page matches.
def find_matches(page_subset, color):
    match_set = []
    for page in page_subset:
        if page in page_list:
            if page in page_child:
                child_subset = find_matches(page_child[page], color)
                if len(child_subset) == 1:
                    match_set.extend(child_subset)
                elif len(child_subset) > 1:
                    match_set.append(page)
                    # Record this container page's color.
                    if page not in page_color:
                        page_color[page] = set()
                    page_color[page].add(color)
            elif page_matches_color(page, color):
                match_set.append(page)
    return match_set

# We don't need color_page_list yet, but we go through the creation process
# now in order to populate page_color for all container pages.
for color in color_list:
    color_page_list[color] = sorted(find_matches(top_list, color))

# Turn txt into html for all normal and default pages.
jpg_height = 200
for page in page_list:
    parse(page, page_txt[page])

# Create a txt listing all flowers without pages, then parse it into html.
if False:
    jpg_height = 50
    unlisted_flowers = sorted([f for f in page_obs if f not in page_list])
    s = '<br/>\n'.join(unlisted_flowers) + '<p/>\n'
    parse("other observations", s)

###############################################################################
# The remaining code is for creating useful lists of pages:
# all pages, and pages sorted by flower color.

# List a single page, indented if it is under a parent.
# (But don't indent it if it is itself a parent, in which case it has is
# already put itself in an indented box.)
def list_page(w, page, indent):
    if indent:
        indent_class = ' indent'
    else:
        indent_class = ''

    if page in page_child:
        # A parent puts itself in a box.
        # The box may be indented, in which case, the remainder of the listing
        # is not indented.
        w.write('<div class="box{indent_class}">\n'.format(indent_class=indent_class))
        indent_class = ''

    w.write('<div class="photo-box{indent_class}">'.format(indent_class=indent_class))

    if page in flower_jpg_list:
        w.write('<a href="{page}.html"><img src="../thumbs/{jpg}.jpg" width="200" height="200" class="list-thumb"></a>{spacer}'.format(page=page, jpg=flower_jpg_list[page][0], spacer=horiz_spacer))

    w.write('{link}</div>\n'.format(link=create_link(page, 2)))

def list_matches(w, match_set, indent, color):
    # Sort by observation count.
    def count_flowers(page):
        return count_matching_obs(page, color, set())[0]

    flower_count = 0
    key_count = 0

    if indent:
        # We're under a parent with an ordered child list.  Retain its order.
        pass
    else:
        # Sort in reverse order of observation count.
        # We initialize the sort with match_set sorted alphabetically.
        # This order is retained for subsets with equal observation counts.
        match_set.sort()
        match_set.sort(key=count_flowers, reverse=True)

    for page in match_set:
        if page in page_child:
            list_page(w, page, indent)
            (k, f) = list_matches(w, find_matches(page_child[page], color),
                                  True, color)
            key_count += 1 + k
            flower_count += f
            w.write('</div>\n')
        else:
            flower_count += 1
            list_page(w, page, indent)

    return (key_count, flower_count)

def write_page_list(page_list, color, color_match):
    s = cStringIO.StringIO()
    (k, f) = list_matches(s, page_list, False, color_match)

    with open(root + "/html/{color}.html".format(color=color), "w") as w:
        title = color.capitalize() + ' flowers'
        write_header(w, title, title)
        w.write('{f} flowers and {k} keys'.format(f=f, k=k))
        w.write(s.getvalue())
        write_footer(w)

for color in color_list:
    write_page_list(color_page_list[color], color, color)

write_page_list(top_list, 'all', None)

for genus in genus_page_list:
    if len(genus_page_list[genus]) > 1:
        did_intro = False
        for page in genus_page_list[genus]:
            if page not in page_parent:
                if not did_intro:
                    print 'No key page exists for the following pages in {genus} spp.:'.format(genus=genus)
                    did_intro = True
                print '  ' + get_full(page, 1)

###############################################################################
# Create pages.js

def count_flowers(page):
    return count_matching_obs(page, None, set())[0]

search_file = root + "/pages.js"
with open(search_file, "w") as w:
    w.write('var pages=[\n')
    for page in sorted(page_list, key=count_flowers, reverse=True):
        w.write('{{page:"{page}"'.format(page=page))
        com = get_com(page)
        if com != page:
            w.write(',com:"{com}"'.format(com=com))
        if page in page_sci:
            sci = page_sci[page]
            elab = get_elab(sci)
            if sci != com:
                w.write(',sci:"{sci}"'.format(sci=sci))
            if elab != sci:
                w.write(',elab:"{elab}"'.format(elab=elab))
        if page in page_child:
            w.write(',key:true')
        w.write('},\n')
    w.write('];\n')

###############################################################################
# Compare the new html files with the prev files.
# Create an HTML file with links to all new files and all modified files.
# (Ignore deleted files.)

file_list = sorted(os.listdir(root + '/html'))
new_list = []
mod_list = []
for name in file_list:
    if name.endswith('.html'):
        if not os.path.isfile(root + '/prev/' + name):
            new_list.append(name)
        elif not filecmp.cmp(root + '/prev/' + name,
                             root + '/html/' + name):
            mod_list.append(name)

if mod_list or new_list:
    mod_file = root + "/html/_mod.html"
    with open(mod_file, "w") as w:
        if new_list:
            w.write('<h1>New files</h1>\n')
            for name in new_list:
                w.write('<a href="{name}">{name}</a><p/>\n'.format(name=name))
        if mod_list:
            w.write('<h1>Modified files</h1>\n')
            for name in mod_list:
                w.write('<a href="{name}">{name}</a><p/>\n'.format(name=name))

    # open the default browser with the created HTML file
    total_list = mod_list + new_list
    if len(total_list) == 1:
        os.startfile(root + '/html/' + total_list[0])
    else:
        os.startfile(mod_file)
else:
    print "No files modified."
