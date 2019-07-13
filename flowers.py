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

class Page:
    pass

    def __init__(self, name):
        if name in name_page:
            print 'Multiple pages created with name "{name}"'.format(name=name)
        self.name = name
        name_page[name] = self

        self.com = None # a common name
        self.sci = None # a scientific name stripped of elaborations
        self.elab = None # an elaborated scientific name

        # Give the page a default common or scientific name as appropriate.
        # Either or both names may be modified later.
        if name.islower():
            # If there isn't an uppercase letter anywhere, it's a common name.
            self.set_com(name)
        else:
            # If there is an uppercase letter somewhere, it's a scientific name.
            self.set_sci(name)

        # self.txt is always initialized elsewhere.

        self.jpg_list = [] # an ordered list of jpg names

        self.parent = set() # an unordered set of parent pages
        self.child = [] # an ordered list of child pages

        # A set of color names that the page is linked from.
        # (Initially this is just the flower colors,
        # but container pages get added later.)
        self.color = set()

        self.taxon_id = None # iNaturalist taxon ID
        self.obs = 0 # number of observations
        self.obs_rg = 0 # number of observations that are research grade
        self.parks = {} # a dictionary of park_name : count

    def set_com(self, com):
        self.com = com
        com_page[com] = self

    # set_sci() can be called with a stripped or elaborated name.
    # Either way, both a stripped and elaborated name are recorded.
    def set_sci(self, sci):
        sci_words = sci.split(' ')
        if len(sci_words) == 1:
            # One word in the scientific name implies a genus.
            elab = ' '.join((sci, 'spp.'))
        elif len(sci_words) == 3:
            # Three words in the scientific name implies a subset of a species.
            # We probably got this name from an iNaturalist observation, and it
            # doesn't have an explicit override, so we can only assume "ssp."
            elab = ' '.join((sci_words[0], sci_words[1], 'ssp.', sci_words[2]))
        elif len(sci_words) == 4:
            # Four words in the scientific name implies a subset of a species
            # with an elaborated subtype specifier.  The specifier is stripped
            # from the 'sci' name.
            elab = sci
            sci = ' '.join((sci_words[0], sci_words[1], sci_words[3]))
        elif sci_words[1] == 'spp.':
            # It is a genus name in elaborated format.  The 'spp.' suffix is
            # stripped from the 'sci' name.
            elab = sci
            sci = sci_words[0]
        else:
            # The name is in the regular "genus species" format, which is the
            # same for both sci and elab
            elab = sci

        self.sci = sci
        self.elab = elab
        sci_page[sci] = self

    def get_com(self):
        if self.com:
            return self.com
        else:
            return self.name

    def format_elab(self):
        elab = self.elab
        if not elab:
            return None
        elif elab[0].isupper():
            return '<i>{elab}</i>'.format(elab=elab)
        else: # it must be in {group_type} {name} format
            elab_words = elab.split(' ')
            return '{type} <i>{name}</i>'.format(type=elab_words[0],
                                                 name=elab_words[1])

    def format_full(self, lines=2):
        com = self.com
        elab = self.format_elab()
        if not com:
            return elab
        elif not elab:
            return com
        elif lines == 1:
            return '{com} ({elab})'.format(com=com, elab=elab)
        else:
            return '{com}<br/>{elab}'.format(com=com, elab=elab)

    def add_jpg(self, jpg):
        self.jpg_list.append(jpg)

    def parse_names(self):
        def repl_com(matchobj):
            com = matchobj.group(1)
            self.set_com(com)
            return ''

        def repl_sci(matchobj):
            sci = matchobj.group(1)
            self.set_sci(sci)
            return ''

        self.txt = re.sub(r'{com:(.*)}\n', repl_com, self.txt)
        self.txt = re.sub(r'{sci:(.*)}\n', repl_sci, self.txt)

    # Check if check_page is an ancestor of this page (for loop checking).
    def is_ancestor(self, check_page):
        if self == check_page:
            return True

        for parent in self.parent:
            if parent.is_ancestor(check_page):
                return True

        return False

    def assign_child(self, child):
        if self.is_ancestor(child):
            print "circular loop when creating link from {parent} to {child}".format(parent=self.name, child=child.name)
        else:
            self.child.append(child)
            child.parent.add(self)

    def parse_children(self):
        # Replace a {child:[page]} link with just {[page]} and record the
        # parent->child relationship.
        def repl_child(matchobj):
            x = matchobj.group(1)
            child = matchobj.group(2)
            suffix = matchobj.group(3)
            sci = matchobj.group(4)
            if not suffix:
                suffix = ''
            # If the child does not exist, don't record the relationship.
            # We don't need to flag an error here, though.  We'll just
            # create the links to the non-existant child, and those links
            # will flag an error when they get parsed.
            if child in name_page:
                child_page = name_page[child]
                self.assign_child(child_page)
                # In addition to linking to the child,
                # also give a scientific name to it.
                if sci:
                    sci = sci[1:] # discard colon
                    child_page.set_sci(sci)
            if x == '+':
                # Replace the {+...} field with two new fields:
                # - a photo that links to the child
                # - a text link to the child
                return ('{' + child + ':' + child + suffix + '.jpg}\n'
                        '{' + child + '}')
            else:
                # Replaced the {child:...} field with a new field:
                # - a text link to the child
                return '{' + child + '}'

        self.txt = re.sub(r'{(child:|\+)([^\}:,]+)(,[-0-9]*)?(:[^\}]+)?}', repl_child, self.txt)

    def create_link(self, lines):
        if self.child:
            style = ' class="parent"'
        else:
            style = ' class="leaf"'
        return '<a href="{name}.html"{style}>{full}</a>'.format(name=self.name, style=style, full=self.format_full(lines))

    def write_parents(self, w):
        for parent in sorted(self.parent):
            w.write('Key to {link}<br/>'.format(link=parent.create_link(1)))
        if self.parent:
            w.write('<p/>')

    def page_matches_color(self, color):
        return (color == None or color in self.color)

    # For containers, sum the observation counts of all children,
    # *but* if a flower is found via multiple paths, count it only once.
    # Two values are returned: (n, rg)
    #   n is the observation count
    #   rg is the research-grade observation count (0 <= rg <= n)
    def count_matching_obs(self, color, match_flowers):
        if self in match_flowers: return (0, 0)

        n = 0
        rg = 0

        # If a container page contains exactly one descendant with a matching
        # color, the container isn't listed on the color page, and the color
        # isn't listed in page_color for the page.  Therefore, we follow all
        # child links blindly and only compare the color when we reach a flower
        # with an observation count.
        if self.obs and self.page_matches_color(color):
            n += self.obs
            rg += self.obs_rg
            match_flowers.add(page)

        for child in self.child:
            (ch_n, ch_rg) = child.count_matching_obs(color, match_flowers)
            n += ch_n
            rg += ch_rg

        return (n, rg)

    # Write the iNaturalist observation data.
    def write_obs(self, w):
        (n, rg) = self.count_matching_obs(None, set())

        sci = self.sci
        if n == 0 and not sci:
            return

        if self.taxon_id:
            link = 'https://www.inaturalist.org/observations/chris_nelson?taxon_id={taxon_id}&order_by=observed_on'.format(taxon_id=self.taxon_id)
        elif sci and sci[0].isupper():
            # iNaturalist can't search by name on a higher level taxon,
            # only a genus or lower.
            link = 'https://www.inaturalist.org/observations/chris_nelson?search_on=names&q={sci}&order_by=observed_on'.format(sci=sci)
        else:
            link = None

        w.write('<p/>\n')

        if link:
            w.write('<a href="{link}" target="_blank">Chris&rsquo;s observations</a>: '.format(link=link))
        else:
            w.write('Chris&rsquo;s observations: ')

        if sci and sci[0].isupper() and sci.count(' ') == 1:
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
            if rg == 1:
                w.write('{n} ({rg} is {rg_txt})'.format(n=n, rg=rg, rg_txt=rg_txt))
            else:
                w.write('{n} ({rg} are {rg_txt})'.format(n=n, rg=rg, rg_txt=rg_txt))

        if not self.child and self.parks:
            w.write('''
<span class="toggle-details" onclick="fn_details(this)">[show details]</span><p/>
<div id="details">
Locations:
<ul>
''')
            for park in sorted(self.parks,
                               key = lambda x: self.parks[x],
                               reverse=True):
                html_park = park.encode('ascii', 'xmlcharrefreplace')
                count = self.parks[park]
                if count == 1:
                    w.write('<li>{park}</li>\n'.format(park=html_park))
                else:
                    w.write('<li>{park}: {count}</li>\n'.format(park=html_park, count=count))
            w.write('</ul></div>\n')
        else:
            w.write('<p/>\n')

    def write_external_links(self, w):
        sci = self.sci
        if not sci[0].isupper():
            # A higher-level classification should be sent with the group type
            # removed.
            space_pos = sci.find(' ')
            stripped = sci[space_pos+1:]
            elab = stripped
        else:
            stripped = sci
            if ' ' not in sci:
                # A one-word genus should be sent as is, not as '[genus] spp.'
                elab = sci
            else:
                # A species or subspecies should be elaborated as necessary.
                elab = self.elab

        w.write('<p/>')

        if self.taxon_id:
            w.write('<a href="https://www.inaturalist.org/taxa/{taxon_id}" target="_blank">iNaturalist</a> &ndash;\n'.format(taxon_id=self.taxon_id))
        else:
            w.write('<a href="https://www.inaturalist.org/search?q={stripped}&source=taxa" target="_blank">iNaturalist</a> &ndash;\n'.format(stripped=stripped))

        w.write('<a href="https://www.calflora.org/cgi-bin/specieslist.cgi?namesoup={elab}" target="_blank">CalFlora</a> &ndash;\n'.format(elab=elab));

        if sci[0].isupper() and ' ' in sci:
            # CalPhotos cannot be searched by genus or higher classification.
            w.write('<a href="https://calphotos.berkeley.edu/cgi/img_query?where-taxon={elab}" target="_blank">CalPhotos</a> &ndash;\n'.format(elab=elab));

        # Jepson uses "subsp." instead of "ssp.", but it also allows us to
        # search with that qualifier left out entirely.
        w.write('<a href="http://ucjeps.berkeley.edu/eflora/search_eflora.php?name={sci}" target="_blank">Jepson eFlora</a><p/>\n'.format(sci=stripped));

    def write_lists(self, w):
        w.write('Flower lists that include this page:<p/>\n')
        w.write('<ul/>\n')

        for color in color_list:
            if color in self.color:
                w.write('<li><a href="{color}.html">{color} flowers</a></li>\n'.format(color=color))

        w.write('<li><a href="all.html">all flowers</a></li>\n')
        w.write('</ul>\n')

    # List a single page, indented if it is under a parent.
    # (But don't indent it if it is itself a parent, in which case it has
    # already put itself in an indented box.)
    def list_page(self, w, indent):
        if indent:
            indent_class = ' indent'
        else:
            indent_class = ''

        if self.child:
            # A parent puts itself in a box.
            # The box may be indented, in which case, the remainder
            # of the listing is not indented.
            w.write('<div class="box{indent_class}">\n'.format(indent_class=indent_class))
            indent_class = ''

        w.write('<div class="photo-box{indent_class}">'.format(indent_class=indent_class))

        if self.jpg_list:
            w.write('<a href="{name}.html"><img src="../thumbs/{jpg}.jpg" width="200" height="200" class="list-thumb"></a>'.format(name=self.name, jpg=self.jpg_list[0]))

        w.write('{link}</div>\n'.format(link=self.create_link(2)))


    # The giant 'parse' function, which turns txt into html
    # and writes the resulting file.
    def parse(self):
        s = self.txt

        def repl_easy(matchobj):
            return repl_easy_dict[matchobj.group(1)]

        # replace the easy (fixed-value) stuff.
        s = repl_easy_regex.sub(repl_easy, s)

        def repl_list(matchobj):
            c = matchobj.group(1)
            c = re.sub(r'\n', r'</li>\n<li>', c)

            # If there's a sublist, its <ul> & </ul> must be on their own lines,
            # in which case we remove the accidental surrounding <li>...</li>.
            c = re.sub(r'<li>(<(/?)ul>)</li>', r'\1', c)

            return '\n<ul>\n<li>{c}</li>\n</ul>\n'.format(c=c)

        s = re.sub(r'\n{-\n(.*?)\n-}\n', repl_list, s, flags=re.DOTALL)

        # Replace {jpgs} with all jpgs that exist for the flower.
        def repl_jpgs(matchobj):
            if self.jpg_list:
                jpgs = ['{{{jpg}.jpg}}'.format(jpg=jpg) for jpg in self.jpg_list]
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

            # If the text after the images appears to be a species link
            # followed by more text, then duplicate and contain the
            # species link so that the following text can either be in
            # the same column or on a different row, depending on the
            # width of the viewport.
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

        s = re.sub(r'((?:\{(?:jpgs|[^\}]+.jpg|https://calphotos.berkeley.edu/[^\}]+)\} *(?:\n(?!\n))?)+)(.*?)(?=\n(\n|\Z))', repl_photo_box, s, flags=re.DOTALL)

        # Replace a pair of newlines with a paragraph separator.
        # (Do this after making specific replacements based on paragraphs,
        # but before replacements that might create empty lines.)
        s = s.replace('\n\n', '\n<p/>\n')

        # Replace {*.jpg} with a thumbnail image and either
        # - a link to the full-sized image, or
        # - a link to a child page.
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

            # Keep trying stuff until we find something in the global jpg_list
            # or until we explicitly give up.
            while jpg not in jpg_list:
                # If the "jpg" name is actually a page name,
                # use the first jpg of that page (if there is one),
                # or drill into its first child (if there is one).
                if jpg in name_page:
                    jpg_page = name_page[jpg]
                    if jpg_page.jpg_list:
                        jpg = jpg_page.jpg_list[0]
                        break

                    if jpg_page.child:
                        jpg = jpg_page.child[0].name
                        continue

                break # give up

            thumb = '../thumbs/{jpg}.jpg'.format(jpg=jpg)

            if link_to_jpg:
                href = '../photos/{jpg}.jpg'.format(jpg=jpg)
            else:
                href = '{link}.html'.format(link=link)

            if jpg in jpg_list:
                # Different formatting for a photo on a key page vs.
                # a leaf page.
                if self.child:
                    img_class = 'page-thumb'
                else:
                    img_class = 'leaf-thumb'
                img = '<a href="{href}"><img src="{thumb}" width="200" height="200" class="{img_class}"></a>'.format(href=href, thumb=thumb, img_class=img_class)
            else:
                img = '<a href="{href}" class="missing"><div class="page-thumb-text"><span>{jpg}</span></div></a>'.format(jpg=jpg, href=href)
                print '{jpg}.jpg missing'.format(jpg=jpg)

            return img

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

            return img

        s = re.sub(r'\{(https://calphotos.berkeley.edu/[^\}]+)\}', repl_calphotos, s)

        # Replace a {[common]:[scientific]} reference with a link to CalFlora.
        # [common] is optional, but the colon must always be present.
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
        # Replace it with a link to one of my pages (if I can).
        def repl_link(matchobj):
            link = matchobj.group(1)
            if link[0] == '-':
                link = link[1:]
                lines = 1
            else:
                lines = 2
            if link in name_page:
                return name_page[link].create_link(lines)
            else:
                print 'Broken link {{{link}}} on page {page}'.format(link=link, page=this.name)
                return '{' + link + '}'

        s = re.sub(r'{([^}]+)}', repl_link, s)

        with open(root + "/html/" + self.name + ".html", "w") as w:
            com = self.com
            elab = self.elab

            if com:
                title = com
                h1 = com
            else:
                # If the page has no common name (only a scientific name),
                # then the h1 header should be italicized and elaborated.
                title = elab
                h1 = self.format_elab()

            # True if an extra line is needed for the scientific name.
            has_sci = (com and elab)
            write_header(w, title, h1, has_sci)
            if has_sci:
                w.write('<b>{elab}</b><p/>\n'.format(elab=self.format_elab()))

            self.write_parents(w)

            w.write(s)
            self.write_obs(w)
            if self.sci:
                self.write_external_links(w)
            w.write('<hr/>\n')
            self.write_lists(w)
            write_footer(w)

        if not self.child and not self.color:
            print 'No color for {name}'.format(name=self.name)

        # record all pages that are within each genus
        sci = self.sci
        if sci and sci[0].isupper():
            pos = sci.find(' ')
            if pos > -1:
                genus = sci[:pos]
                if genus not in genus_page_list:
                    genus_page_list[genus] = []
                genus_page_list[genus].append(self)

###############################################################################
# end of Page class
###############################################################################


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

name_page = {} # page (base file) name -> page
com_page = {} # common name -> page
sci_page = {} # scientific name -> page
genus_page_list = {} # genus name -> list of pages in that genus

# Define a list of supported colors.
color_list = ['blue',
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

def get_name_from_jpg(jpg):
    name = re.sub(r',([-0-9]*)$', r'', jpg)

    if name[0].isupper():
        # If the jpg uses an elaborated name, remove the elaborations to
        # form the final page name.
        sci_words = name.split(' ')
        if len(sci_words) == 4:
            # Four words in the scientific name implies a subset of a species
            # with an elaborated subtype specifier.  The specifier is stripped.
            name = ' '.join((sci_words[0], sci_words[1], sci_words[3]))
        elif len(sci_words) == 2 and sci_words[1] == 'spp.':
            # It is a genus name in elaborated format.  The 'spp.' suffix is
            # stripped.
            name = sci_words[0]

    return name

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

def write_header(w, title, h1, nospace=False):
    if nospace:
        space_class = ' class="nospace"'
    else:
        space_class = ''
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
<div id="search-bg"></div>
<div id="search-container">
<input type="text" id="search" autocapitalize="none" autocorrect="off" autocomplete="off" spellcheck="false" placeholder="search for a flower...">
<div id="autocomplete-box"></div>
</div>
<div id="body">
<h1 id="title"{space_class}>{h1}</h1>
'''.format(title=title, space_class=space_class, h1=h1))


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


# Read the txt for all explicit page files.
for name in page_list:
    page = Page(name)
    with open(root + "/txt/" + name + ".txt", "r") as r:
        page.txt = r.read()

# Create implicit txt for all unassociated jpgs.
# Record jpg names for the jpgs' associated pages
# (whether those pages are old or new).
for jpg in sorted(jpg_list):
    name = get_name_from_jpg(jpg)
    if name in name_page:
        page = name_page[name]
    else:
        page = Page(name)
        page.txt = '{default}'
    page.add_jpg(jpg)

# Read color info from the YAML file.
with open(root + '/color.yaml') as f:
    yaml_data = yaml.safe_load(f)
for name in yaml_data:
    if name in name_page:
        page = name_page[name]
        page.color = set([x.strip() for x in yaml_data[name].split(',')])
        for color in page.color:
            if color not in color_list:
                print 'page {name} uses undefined color {color}'.format(name=name, color=color)
    else:
        print 'colors specified for non-existant page {name}'.format(name=name)

# Perform a first pass on all pages to
# - initialize common and scientific names as specified,
# - detect parent->child relationships among pages.
for page in name_page.itervalues():
    page.parse_names()
    page.parse_children()

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
        elif com in com_page:
            page = com_page[com]
            if not page.sci: # don't override previous info
                page.set_sci(sci)
        else:
            page = None

        if page:
            page.taxon_id = taxon_id
            page.obs += 1
            if rg == 'research':
                page.obs_rg += 1
            if short_park not in page.parks:
                page.parks[short_park] = 0
            page.parks[short_park] += 1

if park_nf_list:
    print "Parks not found:"
    for x in park_nf_list:
        print "  " + repr(x)

# Get a list of pages without parents (top-level pages).
top_list = [x for x in name_page.itervalues() if not x.parent]

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
        if page.child:
            child_subset = find_matches(page.child, color)
            if len(child_subset) == 1:
                match_set.extend(child_subset)
            elif len(child_subset) > 1:
                match_set.append(page)
                # Record this container page's newly discovered color.
                page.color.add(color)
        elif page.page_matches_color(color):
            match_set.append(page)
    return match_set

# We don't need color_page_list yet, but we go through the creation process
# now in order to populate page_color for all container pages.
for color in color_list:
    color_page_list[color] = find_matches(top_list, color)

# Turn txt into html for all normal and default pages.
for page in name_page.itervalues():
    page.parse()

###############################################################################
# The remaining code is for creating useful lists of pages:
# all pages, and pages sorted by flower color.

# helper function for sorting by name
def by_name(page):
    if page.com:
        return page.com.lower()
    else:
        return page.sci.lower()

# match_set can be either a set or list of pages.
# If indent is False, we'll sort them into a list by reverse order of
# observation counts.  If indent is True, match_set must be a list, and
# its order is retained.
def list_matches(w, match_set, indent, color):
    # Sort by observation count.
    def count_flowers(page):
        return page.count_matching_obs(color, set())[0]

    flower_count = 0
    key_count = 0

    if indent:
        # We're under a parent with an ordered child list.  Retain its order.
        match_list = match_set
    else:
        # Sort in reverse order of observation count.
        # We initialize the sort with match_set sorted alphabetically.
        # This order is retained for subsets with equal observation counts.
        match_list = sorted(match_set, key=by_name)
        match_list.sort(key=count_flowers, reverse=True)

    for page in match_list:
        if page.child:
            page.list_page(w, indent)
            (k, f) = list_matches(w, find_matches(page.child, color),
                                  True, color)
            key_count += 1 + k
            flower_count += f
            w.write('</div>\n')
        else:
            flower_count += 1
            page.list_page(w, indent)

    return (key_count, flower_count)

def write_page_list(page_list, color, color_match):
    # We write out the matches to a string first so that we can get
    # the total number of keys and flowers in the list (including children).
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
            if not page.parent:
                if not did_intro:
                    print 'No key page exists for the following pages in {genus} spp.:'.format(genus=genus)
                    did_intro = True
                print '  ' + page.format_full(11)

###############################################################################
# Create pages.js

def count_flowers(page):
    return page.count_matching_obs(None, set())[0]

search_file = root + "/pages.js"
with open(search_file, "w") as w:
    w.write('var pages=[\n')
    # Sort in reverse order of observation count.
    # We initialize the sort by sorting alphabetically.
    # This order is retained for subsets with equal observation counts.
    # This order tie-breaker isn't particularly useful to the user, but
    # it helps prevent pages.js from getting random changes just because
    # the dictionary hashes differently.
    page_list = [x for x in name_page.itervalues()]
    page_list.sort(key=by_name)
    page_list.sort(key=count_flowers, reverse=True)
    for page in page_list:
        w.write('{{page:"{name}"'.format(name=page.name))
        if page.com and page.com != page.name:
            w.write(',com:"{com}"'.format(com=page.com))
        if page.elab and page.elab != page:
            w.write(',sci:"{elab}"'.format(elab=page.elab))
        if page.child:
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
