import re
from unidecode import unidecode

# My files
from files import *
from obs import *
from easy import *

###############################################################################

page_array = [] # array of pages; only appended to; never otherwise altered
name_page = {} # original page name -> page [final file name may vary]
com_page = {} # common name -> page (or 'multiple' if there are name conflicts)
sci_page = {} # scientific name -> page
genus_page_list = {} # genus name -> list of pages in that genus
genus_family = {} # genus name -> family name
family_child_set = {} # family name -> set of top-level pages in that family

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

glossary_taxon_dict = {}

def is_sci(name):
    # If there isn't an uppercase letter anywhere, it's a common name.
    # If there is an uppercase letter somewhere, it's a scientific name.
    # E.g. "Taraxacum officinale" or "family Asteraceae".
    return not name.islower()

def strip_sci(sci):
    sci_words = sci.split(' ')
    if (len(sci_words) >= 2 and
        sci_words[0][0].isupper() and
        sci_words[1][0] == 'X'):
        sci_words[1] = sci_words[1][1:]
        sci = ' '.join(sci_words)
    if len(sci_words) == 4:
        # Four words in the scientific name implies a subset of a species
        # with an elaborated subtype specifier.  The specifier is stripped
        # from the 'sci' name.
        return ' '.join((sci_words[0], sci_words[1], sci_words[3]))
    elif len(sci_words) == 2:
        if sci_words[1] == 'spp.':
            # It is a genus name in elaborated format.  The 'spp.' suffix is
            # stripped from the 'sci' name.
            return sci_words[0]
        elif sci[0].islower():
            # The name is in {type} {name} format (e.g. "family Phrymaceae").
            # Strip the type from the 'sci' name.
            return sci_words[1]
    # The name is already in a fine stripped format.
    return sci

def elaborate_sci(sci):
    sci_words = sci.split(' ')
    if len(sci_words) == 1:
        # One word in the scientific name implies a genus.
        return ' '.join((sci, 'spp.'))
    elif len(sci_words) == 3:
        # Three words in the scientific name implies a subset of a species.
        # We probably got this name from an iNaturalist observation, and it
        # doesn't have an explicit override, so we can only assume "ssp."
        return ' '.join((sci_words[0], sci_words[1], 'ssp.', sci_words[2]))
    # The name is already in a fine elaborated format.
    return sci

def find_page2(com, sci):
    if sci:
        sci = strip_sci(sci)
        if sci in sci_page:
            return sci_page[sci]

    if com:
        page = None
        if com in name_page:
            page = name_page[com]
        elif com in com_page and com_page[com] != 'multiple':
            page = com_page[com]

        if page and sci and page.sci and page.sci != sci:
            # If the common name matches a page with a different scientific
            # name, it's treated as not a match.
            return None
        else:
            return page

    return None

def find_page1(name):
    if is_sci(name):
        return find_page2(None, name)
    else:
        return find_page2(name, None)

###############################################################################

def sort_pages(page_set, color=None, with_depth=False):
    # helper function to sort by name
    def by_name(page):
        if page.com:
            return page.com.lower()
        else:
            return page.sci.lower()

    # helper function to sort by hierarchical depth (parents before children)
    def by_depth(page):
        if not page.parent:
            return 0

        parent_depth = 0
        for parent in page.parent:
            parent_depth = max(parent_depth, by_depth(parent))
        return parent_depth + 1

    # helper function to sort by observation count
    def count_flowers(page):
        obs = Obs(color)
        page.count_matching_obs(obs)
        return obs.n

    # Sort in reverse order of observation count.
    # We initialize the sort with match_set sorted alphabetically.
    # We then sort by hierarchical depth, retaining the previous alphabetical
    # order for ties.  Finally, we sort by observation count, again retaining
    # the most recent order for ties.
    page_list = sorted(page_set, key=by_name)
    if with_depth:
        page_list.sort(key=by_depth)
    page_list.sort(key=count_flowers, reverse=True)
    return page_list

###############################################################################

class Page:
    pass

    def __init__(self, name):
        self.set_name(name)
        self.name_from_txt = False # True if the name came from a txt filename

        self.index = len(page_array)
        page_array.append(self)

        self.com = None # a common name
        self.sci = None # a scientific name stripped of elaborations
        self.elab = None # an elaborated scientific name
        self.family = None # the scientific family
        self.level = None # taxonomic level: above, genus, species, or below

        self.no_sci = False # true if it's a key page for unrelated species
        self.no_family = False # true if it's a key page for unrelated genuses

        self.top_level = None # 'flowering plants', 'ferns', etc.

        self.elab_calflora = None
        self.elab_calphotos = None
        self.elab_jepson = None
        self.elab_inaturalist = None

        # the iNaturalist common name.
        # must be None if the common name isn't set.
        # if valid, must be different than the common name.
        self.icom = None

        self.autogenerated = False # true if it's an autogenerated family page

        self.ext_photo_list = [] # list of (text, calphotos_link) tuples
        self.genus_complete = None # indicates the completeness of the genus
        self.genus_key_incomplete = False # indicates if the key is complete
        self.species_complete = None # the same for the species
        self.species_key_incomplete = False

        # Give the page a default common or scientific name as appropriate.
        # Either or both names may be modified later.
        if is_sci(name):
            self.set_sci(name)
        else:
            self.set_com(name)

        self.txt = ''
        self.key_txt = ''
        self.jpg_list = [] # an ordered list of jpg names

        self.parent = set() # an unordered set of parent pages
        self.child = [] # an ordered list of child pages
        self.key = False # true if the page has child pages or CalFlora links

        # A set of color names that the page is linked from.
        # (Initially this is just the flower colors,
        # but container pages get added later.)
        self.color = set()

        self.taxon_id = None # iNaturalist taxon ID
        self.obs_n = 0 # number of observations
        self.obs_rg = 0 # number of observations that are research grade
        self.parks = {} # a dictionary of park_name : count
        self.month = [0] * 12

        self.glossary = None

    def url(self):
        return unidecode(self.name)

    def change_name_to_sci(self):
        del name_page[self.name]
        self.set_name(self.sci)

    def set_name(self, name):
        if name in name_page:
            print(f'Multiple pages created with name "{name}"')
        self.name = name
        name_page[name] = self

    def set_com(self, com):
        self.com = com
        if com in com_page:
            if com_page[com] != self:
                com_page[com] = 'multiple'
        else:
            com_page[com] = self

    # set_sci() can be called with a stripped or elaborated name.
    # Either way, both a stripped and elaborated name are recorded.
    def set_sci(self, sci):
        sci_words = sci.split(' ')
        if (len(sci_words) >= 2 and
            sci_words[0][0].isupper() and
            sci_words[1][0] == 'X'):
            sci_words[1] = sci_words[1][1:]
            sci = ' '.join(sci_words)
            self.is_hybrid = True
        else:
            self.is_hybrid = False

        elab = elaborate_sci(sci)
        sci = strip_sci(sci)

        if sci in sci_page and sci_page[sci] != self:
            print(f'Same scientific name ({sci}) set for {sci_page[sci].name} and {self.name}')

        if elab[0].islower():
            self.level = 'above'
        else:
            sci_words = sci.split(' ')
            if len(sci_words) == 1:
                self.level = 'genus'
            elif len(sci_words) == 2:
                self.level = 'species'
            else:
                self.level = 'below'

        self.sci = sci
        self.elab = elab
        sci_page[sci] = self

    def set_top_level(self, top_level, tree_top):
        if self.top_level == None:
            self.top_level = top_level
            for child in self.child:
                child.set_top_level(top_level, tree_top)
        elif self.top_level == top_level:
            # The top level has already been set
            # (which implies that its children have had it set, too).
            return
        else:
            print(f'{name} is under both {self.top_level} and {top_level} ({tree_top})')

    def set_family(self):
        if self.family or self.no_family:
            # The page's family has already been set
            # (which implies that its children have had their family set, too).
            return

        # set the family of all children
        for child in self.child:
            child.set_family()

        # if all children appear share the same family, use that as the
        # current page's family.  But if the children have different families,
        # set self.no_family.
        for child in self.child:
            if child.no_family:
                self.family = None
                self.no_family = True
                return
            elif child.family:
                if self.family == None:
                    self.family = child.family
                elif self.family != child.family:
                    self.family = None
                    self.no_family = True
                    return
            else:
                # The child doesn't know its family, but also isn't obviously
                # in multiple families.  Just ignore it.
                pass

        # If we didn't set the family and also didn't return with no_family,
        # it's because we have no children or the children don't have a clear
        # family.  Try to get the family from the genus instead.
        if not self.family and self.sci:
            genus = self.sci.split(' ')[0]
            if genus in genus_family:
                self.family = genus_family[genus]

        family = self.family
        if family:
            # This page has a family.  family_child_set keeps track of the
            # top-level pages within the family, so add this page to the set
            # and remove its children.
            if family not in family_child_set:
                family_child_set[family] = set()
            family_child_set[family].add(self)
            for child in self.child:
                if child in family_child_set[family]:
                    family_child_set[family].remove(child)

    def get_com(self):
        if self.com:
            return self.com
        else:
            return self.name

    def format_com(self):
        com = self.com
        if not com:
            return None
        return easy_sub_safe(com)

    def format_elab(self):
        elab = self.elab
        if not elab:
            return None
        elif self.level == 'above':
            (gtype, name) = elab.split(' ')
            return f'{gtype} <i>{name}</i>'
        else:
            if self.is_hybrid:
                elab = re.sub(r' ', ' &times; ', elab)
            return f'<i>{elab}</i>'

    def format_full(self, lines=2):
        com = self.format_com()
        elab = self.format_elab()
        if not com:
            return elab
        elif not elab:
            return com
        elif lines == 1:
            return f'{com} ({elab})'
        else:
            return f'{com}<br/>{elab}'

    def add_jpg(self, jpg):
        self.jpg_list.append(jpg)

    def get_jpg(self):
        if self.jpg_list:
            return self.jpg_list[0]
        else:
            # Search this key page's children for a jpg to use.
            for child in self.child:
                jpg = child.get_jpg()
                if jpg:
                    return jpg
            return None

    def get_ext_photo(self):
        if self.ext_photo_list:
            return self.ext_photo_list[0]
        else:
            # Search this key page's children for an external photo to use.
            for child in self.child:
                ext_photo = child.get_ext_photo()
                if ext_photo:
                    return ext_photo
            return None

    def remove_comments(self):
        self.txt = re.sub(r'^#.*\n', '', self.txt, flags=re.MULTILINE)

    def parse_names(self):
        def repl_com(matchobj):
            com = matchobj.group(1)
            self.set_com(com)
            return ''

        def repl_sci(matchobj):
            sci = matchobj.group(1)
            if sci == 'n/a':
                self.no_sci = True
            else:
                self.set_sci(sci)
            return ''

        self.txt = re.sub(r'^com:\s*(.*?)\s*?\n',
                          repl_com, self.txt, flags=re.MULTILINE)
        self.txt = re.sub(r'^sci:\s*(.*?)\s*?\n',
                          repl_sci, self.txt, flags=re.MULTILINE)

    def set_sci_alt(self, sites, elab):
        if 'f' in sites:
            self.elab_calflora = elab
        if 'p' in sites:
            self.elab_calphotos = elab
        if 'j' in sites:
            self.elab_jepson = elab
        if 'i' in sites:
            self.elab_inaturalist = elab

    def set_complete(self, matchobj):
        if matchobj.group(1) == 'x':
            if self.genus_complete != None:
                print(f'{self.name} has both x:{self.genus_complete} and x:{matchobj.group(3)}')
            self.genus_complete = matchobj.group(3)
            if matchobj.group(2):
                self.genus_key_incomplete = True
        else:
            if self.species_complete != None:
                print(f'{self.name} has both xx:{self.species_complete} and xx:{matchobj.group(3)}')
            self.species_complete = matchobj.group(3)
            if matchobj.group(2):
                self.species_key_incomplete = True
        return ''

    def set_colors(self, color_str):
        if self.color:
            print(f'color is defined more than once for page {self.name}')

        self.color = set([x.strip() for x in color_str.split(',')])

        # record the original order of colors in case we want to write
        # it out.
        self.color_txt = color_str

        # check for bad colors.
        for color in self.color:
            if color not in color_list:
                print(f'page {self.name} uses undefined color {color}')

    def record_ext_photo(self, label, link):
        if (label, link) in self.ext_photo_list:
            print(f'{link} is specified more than once for page {self.name}')
        else:
            if label:
                label = easy_sub_safe(label)
            self.ext_photo_list.append((label, link))

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
            print(f'circular loop when creating link from {self.name} to {child.name}')
        elif self in child.parent:
            print(f'{child.name} added as child of {self.name} twice')
        else:
            self.child.append(child)
            child.parent.add(self)
            self.key = True

    def expand_genus(self, sci):
        if (self.cur_genus and len(sci) >= 3 and
            sci[0:3] == self.cur_genus[0] + '. '):
            return self.cur_genus + sci[2:]
        else:
            return sci

    def parse_children(self):
        # Replace a ==[name] link with ==[page] and record the
        # parent->child relationship.
        def repl_child(matchobj):
            com = matchobj.group(1)
            suffix = matchobj.group(2)
            sci = matchobj.group(3)
            if not suffix:
                suffix = ''
            if not sci:
                if is_sci(com):
                    sci = com
                    com = ''
                else:
                    sci = ''
            # ==com[,suffix][:sci] -> creates a child relationship with the
            #   page named by [com] or [sci] and creates two links to it:
            #   an image link and a text link.
            #   If a suffix is specified, the jpg with that suffix is used
            #   for the image link.
            #   If [:sci] isn't specified, a scientific name can be used
            #   in place of [com].
            #   If the child page doesn't exist, it is created.  If the
            #   child page is missing a common or scientific name that
            #   is supplied by the child link, that name is added to the child.
            #   The scientific name can be in elaborated or stripped format.
            #   The genus can also be abbreviated as '[cap.letter]. '
            if sci:
                # If the child's genus is abbreviated, expand it using
                # the genus of the current page.
                sci = self.expand_genus(sci)
            child_page = find_page2(com, sci)
            if not child_page:
                # If the child does not exist, create it.
                # The name for the page depends on what names were provided
                # and whether any collide with existing names.
                if not com:
                    strip = strip_sci(sci)
                    child_page = Page(strip)
                elif com in com_page:
                    # The common name is shared by a flower with a
                    # different scientific name.
                    if not sci:
                        print(f'page {self.name} has ambiguous child {com}')
                        return '==' + com + suffix

                    if com in name_page:
                        if name_page[com].name_from_txt:
                            # The existing user of the name has priority since
                            # its name came from the name of its txt file.
                            pass
                        else:
                            # The user didn't explicitly say that the previous
                            # user of the common name should name its page that
                            # way.  Since we now know that there are two with
                            # the same name, *neither* of them should use the
                            # common name as the page name.  So change the other
                            # page's page name to its scientific name.
                            name_page[com].change_name_to_sci()
                        strip = strip_sci(sci)
                        child_page = Page(strip)
                    else:
                        # All other pages that use the same common name have
                        # been explicitly given a different page name.  This
                        # (presumably intentionally) leaves the page name
                        # available for this child page.
                        child_page = Page(com)
                else:
                    # Prefer the common name in most cases.
                    child_page = Page(com)
            name = child_page.name
            self.assign_child(child_page)
            if com:
                if child_page.com:
                    if com != child_page.com:
                        print(f"page {self.name} refers to child {com}:{sci}, but the common name doesn't match")
                else:
                    child_page.set_com(com)
            if sci:
                child_page.set_sci(sci)

            # Replace the =={...} field with a simplified =={name,suffix} line.
            # This will create the appropriate link later in the parsing.
            return '==' + str(child_page.index) + suffix

        # If the page's genus is explicitly specified,
        # make it the default for child abbreviations.
        if self.level in ('genus', 'species', 'below'):
            self.cur_genus = self.sci.split(' ')[0]
        else:
            self.cur_genus = None

        c_list = []
        data_object = self
        for c in self.txt.split('\n'):
            matchobj = re.match(r'==\s*([^:]*?)\s*?(,[-0-9]\S*|,)?\s*?(?::\s*(.+?))?\s*$', c)
            if matchobj:
                c_list.append(repl_child(matchobj))
                data_object = self.child[-1]
                continue

            matchobj = re.match(r'sci([_fpji]+):\s*(.*?)$', c)
            if matchobj:
                data_object.set_sci_alt(matchobj.group(1),
                                        self.expand_genus(matchobj.group(2)))
                continue

            matchobj = re.match(r'\s*(?:([^:\n]*?)\s*:\s*)?(https://(?:calphotos.berkeley.edu/|www.calflora.org/cgi-bin/noccdetail.cgi)[^\s]+)\s*?$', c)
            if matchobj:
                # Attach the external photo to the current child, else to self.
                data_object.record_ext_photo(matchobj.group(1),
                                             matchobj.group(2))
                continue

            matchobj = re.match(r'color:(.*)$', c)
            if matchobj:
                data_object.set_colors(matchobj.group(1))
                continue

            matchobj = re.match(r'(x|xx):\s*(!?)(none|ba|ca|any|hist|rare|hist/rare|more|uncat)$', c)
            if matchobj:
                data_object.set_complete(matchobj)
                continue

            if c in ('', '[', ']'):
                data_object = self

            c_list.append(c)
        self.txt = '\n'.join(c_list) + '\n'

    def link_style(self):
        if self.autogenerated:
            return 'family'
        elif self.key:
            return 'parent'
        elif self.jpg_list:
            return 'leaf'
        else:
            return 'unobs'

    def create_link(self, lines):
        return f'<a href="{self.url()}.html" class="{self.link_style()}">{self.format_full(lines)}</a>'

    def write_parents(self, w):
        for parent in sort_pages(self.parent):
            if not parent.autogenerated:
                w.write(f'Key to {parent.create_link(1)}<br/>\n')
        if self.parent:
            w.write('<p/>\n')

    def page_matches_color(self, color):
        return (color == None or color in self.color)

    def count_matching_obs(self, obs):
        obs.count_matching_obs(self)

    # Write the iNaturalist observation data.
    def write_obs(self, w):
        obs = Obs(None)
        self.count_matching_obs(obs)

        if obs.n == 0 and not self.sci:
            return

        if self.taxon_id:
            link = f'https://www.inaturalist.org/observations/chris_nelson?taxon_id={self.taxon_id}&order_by=observed_on'
        elif self.sci:
            elab = self.choose_elab(self.elab_inaturalist)
            sci = strip_sci(elab)
            link = f'https://www.inaturalist.org/observations/chris_nelson?taxon_name={sci}&order_by=observed_on'
        else:
            link = None

        obs.write_obs(link, w)

    def choose_elab(self, elab_alt):
        if elab_alt and elab_alt != 'n/a':
            elab = elab_alt
        else:
            elab = self.elab
        elab_words = elab.split(' ')
        if len(elab_words) == 2 and '|' not in elab:
            # Always strip the "spp." suffix or [lowercase type] prefix.
            elab = strip_sci(elab)
        return elab

    def write_external_links(self, w):
        sci = self.sci
        if self.level == 'below':
            # Anything below species level should be elaborated as necessary.
            elab = self.elab
        else:
            # A one-word genus should be sent as is, not as '[genus] spp.'
            # A higher-level classification should be sent with the group type
            # removed.
            elab = sci

        w.write('<p/>')

        elab_list = []
        link_list = {}

        def add_link(elab, elab_alt, link):
            if elab_alt == 'n/a':
                elab = 'not listed'
                link = re.sub(r'<a ', '<a class="missing" ', link)
            elab = re.sub(r'\|', ' / ', elab)
            if elab not in link_list:
                elab_list.append(elab)
                link_list[elab] = []
            link_list[elab].append(link)

        if self.taxon_id:
            elab = self.choose_elab(self.elab_inaturalist)
            sci = strip_sci(elab)
            add_link(elab, None, f'<a href="https://www.inaturalist.org/taxa/{self.taxon_id}" target="_blank">iNaturalist</a>')
        else:
            elab = self.choose_elab(self.elab_inaturalist)
            sci = strip_sci(elab)
            if self.is_hybrid:
                sci = re.sub(r' ', ' \xD7 ', sci)
            add_link(elab, None, f'<a href="https://www.inaturalist.org/taxa/search?q={sci}&view=list" target="_blank">iNaturalist</a>')

        if self.level != 'above' or self.elab.startswith('family '):
            # CalFlora can be searched by family,
            # but not by other high-level classifications.
            elab = self.choose_elab(self.elab_calflora)
            add_link(elab, self.elab_calflora, f'<a href="https://www.calflora.org/cgi-bin/specieslist.cgi?namesoup={elab}" target="_blank">CalFlora</a>');

        if self.level in ('species', 'below'):
            # CalPhotos cannot be searched by high-level classifications.
            # It can be searched by genus, but I don't find that at all useful.
            elab = self.choose_elab(self.elab_calphotos)
            if elab != self.elab:
                # CalPhotos can search for multiple names, and for cases such
                # as Erythranthe, it may have photos under both names.
                # Use both names when linking to CalPhotos, but for simplicity
                # list only the txt-specified name in the HTML listing.
                expanded_elab = self.elab + '|' + elab
            else:
                expanded_elab = elab
            # rel-taxon=begins+with -> allows matches with lower-level detail
            add_link(elab, self.elab_calphotos, f'<a href="https://calphotos.berkeley.edu/cgi/img_query?rel-taxon=begins+with&where-taxon={expanded_elab}" target="_blank">CalPhotos</a>');

        if self.level != 'above' or self.elab.startswith('family '):
            # Jepson can be searched by family,
            # but not by other high-level classifications.
            elab = self.choose_elab(self.elab_jepson)
            # Jepson uses "subsp." instead of "ssp.", but it also allows us to
            # search with that qualifier left out entirely.
            sci = strip_sci(elab)
            add_link(elab, self.elab_jepson, f'<a href="http://ucjeps.berkeley.edu/eflora/search_eflora.php?name={sci}" target="_blank">Jepson&nbsp;eFlora</a>');

        if self.level in ('genus', 'species', 'below'):
            elab = self.choose_elab(self.elab_calflora)
            genus = elab.split(' ')[0]
            # srch=t -> search
            # taxon={name} -> scientific name to filter for
            # group=none -> just one list; not annual, perennial, etc.
            # sort=count -> sort from most records to fewest
            #   (removed because it annoyingly breaks up subspecies)
            # fmt=photo -> list results with info + sample photos
            # y={},x={},z={} -> longitude, latitude, zoom
            # wkt={...} -> search polygon with last point matching the first
            add_link(elab, self.elab_calflora, f'<a href="https://www.calflora.org/entry/wgh.html#srch=t&taxon={genus}&group=none&fmt=photo&y=37.5&x=-122&z=8&wkt=-123.1+38,-121.95+38,-121.05+36.95,-122.2+36.95,-123.1+38" target="_blank">Bay&nbsp;Area&nbsp;species</a>')

        link_list_txt = []
        for elab in elab_list:
            txt = ' &ndash;\n'.join(link_list[elab])
            if len(elab_list) > 1:
                txt = f'{elab}: {txt}'
            link_list_txt.append(txt)
        txt = '</li>\n<li>'.join(link_list_txt)

        if len(elab_list) > 1:
            w.write(f'<p class="list-head">Not all sites agree about the scientific name:</p>\n<ul>\n<li>{txt}</li>\n</ul>\n')
        else:
            w.write(f'{txt}<p/>\n')

    def write_lists(self, w):
        if self.top_level != 'flowering plants':
            return

        if not self.child and not self.jpg_list:
            return

        w.write('<p class="list-head">Flower lists that include this page:</p>\n')
        w.write('<ul>\n')

        for color in color_list:
            if color in self.color:
                w.write(f'<li><a href="{color}.html">{color} flowers</a></li>\n')

        w.write('<li><a href="all.html">all flowers</a></li>\n')
        w.write('</ul>\n')

    # List a single page, indented if it is under a parent.
    def list_page(self, w, indent, has_children):
        if indent:
            indent_class = ' indent'
        else:
            indent_class = ''

        if has_children:
            # A parent with listed children puts itself in a box.
            # The box may be indented depending on the indent parameter.
            # The page is then not indented within the box.
            w.write(f'<div class="box{indent_class}">\n')
            indent_class = ''

        w.write(f'<div class="list-box{indent_class}">')

        if self.jpg_list:
            w.write(f'<a href="{self.url()}.html"><img src="../thumbs/{self.jpg_list[0]}.jpg" width="200" height="200" class="list-thumb"></a>')

        w.write(f'{self.create_link(2)}</div>\n')

    def get_ancestor_set(self):
        ancestor_set = self.parent.copy()
        for parent in self.parent:
            ancestor_set.update(parent.get_ancestor_set())
        return ancestor_set

    def cross_out_children(self, page_list):
        if self in page_list:
            page_list.remove(self)
        for child in self.child:
            child.cross_out_children(page_list)

    def set_glossary(self, glossary):
        if self.glossary:
            # We seem to be setting the glossary via two different
            # tree paths.  Make sure that the parent taxon's glossary
            # is the same on both paths.
            if self.name in glossary_taxon_dict:
                if glossary != self.glossary.glossary_parent:
                    print(f'{self.name} has two different parent glossaries')
            else:
                if glossary != self.glossary:
                    print(f'{self.name} gets two different glossaries')

            # No need to continue the tree traversal through this node
            # since it and its children have already set the glossary.
            return

        if self.name in glossary_taxon_dict:
            # Append the parent glossary list to the taxon's assigned
            # glossary list.
            sub_glossary = glossary_taxon_dict[self.name]
            sub_glossary.set_parent(glossary)
            glossary = sub_glossary

        self.glossary = glossary

        for child in self.child:
            child.set_glossary(glossary)

    def parse(self):
        s = self.txt
        s = re.sub(r'^\n+', '', s)
        s = re.sub(r'\n*$', '\n', s, count=1)

        def end_paragraph(start_list=False):
            nonlocal p_start
            if p_start == None:
                return

            if start_list:
                p_tag = '<p class="list-head">'
            else:
                p_tag = '<p>'
            c_list[p_start] = p_tag + c_list[p_start]
            c_list[-1] += '</p>'
            p_start = None

        def end_child_text():
            nonlocal child_start, c_list
            if child_start == None:
                return

            child = page_array[int(child_matchobj.group(1))]
            suffix = child_matchobj.group(2)
            if not suffix:
                suffix = ''

            text = '\n'.join(c_list[child_start:])
            c_list = c_list[:child_start]
            child_start = None

            # Give the child a copy of the text from the parent's key.
            # The child can use this (pre-parsed) text if it has no text
            # of its own.
            if ((self.level == 'genus' and child.level in ('species', 'below')) or
                (self.level == 'species' and child.level == 'below') or
                not child.key_txt):
                child.key_txt = text

            link = child.create_link(2)

            name = child.name
            jpg = None
            if suffix:
                if name + suffix in jpg_list:
                    jpg = name + suffix
                else:
                    print(name + suffix + '.jpg not found on page ' + self.name)

            if not jpg:
                jpg = child.get_jpg()

            if not jpg:
                ext_photo = child.get_ext_photo()

            if jpg:
                if self.autogenerated:
                    img_class = 'list-thumb'
                else:
                    img_class = 'page-thumb'
                img = f'<a href="{child.url()}.html"><img src="../thumbs/{jpg}.jpg" width="200" height="200" class="{img_class}"></a>'
            elif ext_photo:
                img = f'<a href="{child.url()}.html" class="enclosed {child.link_style()}"><div class="page-thumb-text">'
                n_photos = len(child.ext_photo_list)
                if n_photos > 1:
                    photo_text = f'photos &times; {n_photos}'
                elif ext_photo[0]:
                    photo_text = ext_photo[0]
                else:
                    photo_text = 'photo'
                img += f'<span>{photo_text}</span>'
                img += '</div></a>'
            else:
                img = None

            if not img:
                c_list.append('<p>' + link + '</p>\n' + text)
            elif text:
                # Duplicate and contain the text link so that the following text
                # can either be below the text link and next to the image or
                # below both the image and text link, depending on the width of
                # the viewport.
                c_list.append(f'<div class="flex-width"><div class="photo-box">{img}\n<span class="show-narrow">{link}</span></div><span><span class="show-wide">{link}</span>{text}</span></div>')
            else:
                c_list.append(f'<div class="photo-box">{img}\n<span>{link}</span></div>')

        # replace the easy (fixed-value) stuff.
        # Break the text into lines, then perform easy substitutions on
        # non-keyword lines and decorate bullet lists.
        c_list = []
        p_start = None
        child_start = None
        list_depth = 0
        bracket_depth = 0
        for c in s.split('\n'):
            matchobj = re.match(r'\.*', c)
            new_list_depth = matchobj.end()
            if new_list_depth:
                end_paragraph(True)
            if new_list_depth > list_depth+1:
                print('Jump in list depth on page ' + self.name)
            while list_depth < new_list_depth:
                if list_depth == 0:
                    c_list.append('<ul>')
                else:
                    c_list.append('<ul class="list-sub">')
                list_depth += 1
            while list_depth > new_list_depth:
                c_list.append('</ul>')
                list_depth -= 1
            c = c[list_depth:].strip()

            matchobj = re.match(r'==(\d+)(,[-0-9]\S*|,)?\s*$', c)
            if matchobj:
                end_paragraph()
                end_child_text()
                child_matchobj = matchobj
                child_start = len(c_list)
                continue

            if c == '[':
                end_paragraph()
                end_child_text()
                c_list.append('<div class="box">')
                bracket_depth += 1
                continue

            if c == ']':
                end_paragraph()
                end_child_text()
                c_list.append('</div>')
                bracket_depth -= 1
                continue

            # Replace HTTP links in the text with ones that open a new tab.
            # (Presumably they're external links or they'd be in {...} format.)
            c = re.sub(r'<a href=', '<a target="_blank" href=', c)

            if list_depth:
                c_list.append(f'<li>{c}</li>')
                continue

            if c == '':
                end_paragraph()
                end_child_text()
                continue

            if p_start == None:
                p_start = len(c_list)
            c_list.append(c)
        end_paragraph()
        end_child_text()

        if bracket_depth != 0:
            print(f'"[" and "]" bracket depth is {bracket_depth} on page {self.name}')

        s = '\n'.join(c_list)
        self.txt = s

    def parse2(self):
        # Replace {-[name]} with an inline link to the page.
        def repl_link(matchobj):
            name = matchobj.group(1)
            page = find_page1(name)
            if page:
                return page.create_link(1)
            else:
                print(f'Broken link {{-{name}}} on page {self.name}')
                return '{-' + name + '}'

        # Use the text supplied in the text file if present.
        # Otherwise use the key text from its parent.
        # If the page's text file contains only metadata (e.g.
        # scientific name or color) so that the remaining text is
        # blank, then use the key text from its parent in that case, too.
        if re.search('\S', self.txt):
            s = self.txt
        else:
            s = self.key_txt

        s = link_figures(self.name, s)
        s = re.sub(r'{-([^}]+)}', repl_link, s)
        s = easy_sub(s)
        s = self.glossary.link_glossary_words(s, is_glossary=False)
        self.txt = s

    def any_parent_within_level(self, within_level_list):
        for parent in self.parent:
            if parent.level == None:
                if parent.any_parent_within_level(within_level_list):
                    return True
            elif parent.level in within_level_list:
                return True
        return False

    def is_top_of(self, level):
        if level == 'genus':
            within_level_list = ('genus', 'species', 'below')
        else:
            within_level_list = ('species', 'below')
        is_top_of_level = (self.level in within_level_list)
        if self.any_parent_within_level(within_level_list):
            is_top_of_level = False
        return is_top_of_level

    def write_html(self):
        def write_complete(w, complete, key_incomplete, is_top, top, members):
            if (self.child or
                (top == 'genus' and self.level != 'genus') or
                (top == 'species' and self.level != 'species')):
                other = ' other'
            else:
                other = ''
            if is_top:
                if complete == None:
                    if top == 'genus':
                        w.write(f'<b>Caution: There may be{other} {members} of this {top} not yet included in this guide.</b>')
                    else:
                        return # Don't write the <p/> at the end
                elif complete == 'none':
                    if top == 'genus':
                        print("x:none used for " + self.name)
                    else:
                        w.write('This species has no subspecies or variants.')
                elif complete == 'uncat':
                    if top == 'genus':
                        print("x:uncat used for " + self.name)
                    else:
                        w.write("This species has subspecies or variants that don't seem worth distinguishing.")
                elif complete == 'more':
                    w.write(f'<b>Caution: There are{other} {members} of this {top} not yet included in this guide.</b>')
                else:
                    prolog = f'There are no{other}'
                    if complete == 'hist':
                        prolog = f"Except for historical records that I'm ignoring, there are no{other}"
                    elif complete == 'rare':
                        prolog = f"Except for extremely rare plants that I don't expect to encounter, there are no{other}"
                    elif complete == 'hist/rare':
                        prolog = f"Except for old historical records and extremely rare plants that I don't expect to encounter, there are no{other}"

                    epilog = 'in the bay area'
                    if complete == 'ca':
                        epilog = 'in California'
                    elif complete == 'any':
                        epilog = 'anywhere'

                    w.write(f'{prolog} {members} of this {top} {epilog}.')
                if key_incomplete:
                    w.write(f'<br/>\n<b>Caution: The key to distinguish these {members} is not complete.</b>')
                w.write('<p/>\n')
            elif complete:
                if top == 'genus':
                    print(f'{self.name} uses the x: keyword but is not the top of genus')
                else:
                    print(f'{self.name} uses the xx: keyword but is not the top of species')

        def format_br(br):
            # br is True if there is more text on the next line.
            # br is False at the end of the 'paragraph'.
            if br:
                return '<br/>\n'
            else:
                return '<p/>\n'

        with open(root_path + "/html/" + self.url() + ".html",
                  "w", encoding="utf-8") as w:
            com = self.com
            elab = self.elab

            if com:
                title = self.format_com()
                h1 = title
            else:
                # If the page has no common name (only a scientific name),
                # then the h1 header should be italicized and elaborated.
                title = elab
                h1 = self.format_elab()

            # True if an extra line is needed for the scientific name
            # and/or family name.
            has_sci = (com and elab)
            family = self.family
            if family:
                # Do not emit a line for the family if:
                # - the current page *is* the family page, or
                # - the family page is an explict key and this page's
                #   immediate parent (in which case it'll be listed as
                #   a key page instead).
                family_page = sci_page[family]
                has_family = not (family == self.sci or
                                  (not family_page.autogenerated and
                                   family_page in self.parent))
            else:
                has_family = False
            write_header(w, title, h1, nospace=has_sci or has_family)

            if self.icom:
                w.write(f'(<b>{self.icom}</b>){format_br(elab)}')

            if has_sci:
                w.write(f'<b>{self.format_elab()}</b>{format_br(has_family)}')
            if has_family:
                family_link = family_page.create_link(1)
                w.write(f'{family_link}<p/>\n')

            self.write_parents(w)

            is_top_of_genus = self.is_top_of('genus')
            is_top_of_species = self.is_top_of('species')
            write_complete(w,
                           self.genus_complete, self.genus_key_incomplete,
                           is_top_of_genus, 'genus', 'species')
            write_complete(w,
                           self.species_complete, self.species_key_incomplete,
                           is_top_of_species, 'species', 'members')

            w.write('<hr/>\n')

            if len(self.jpg_list) or len(self.ext_photo_list):
                w.write('<div class="photo-box">\n')

                for jpg in self.jpg_list:
                    w.write(f'<a href="../photos/{jpg}.jpg"><img src="../thumbs/{jpg}.jpg" width="200" height="200" class="leaf-thumb"></a>\n')

                for (label, link) in self.ext_photo_list:
                    w.write(f'<a href="{link}" target="_blank" class="enclosed"><div class="leaf-thumb-text">')
                    if label:
                        w.write('<span>')
                    if 'calphotos' in link:
                        text = 'CalPhotos'
                    elif 'calflora' in link:
                        text = 'CalFlora'
                    else:
                        text = 'external photo'
                    w.write(f'<span style="text-decoration:underline;">{text}</span>')
                    if label:
                        w.write(f'<br/>{label}</span>')
                    w.write('</div></a>\n')

                w.write('</div>\n')

            s = self.txt
            w.write(s)

            if self.jpg_list or self.ext_photo_list or s:
                w.write('<hr/>\n')

            self.write_obs(w)
            if self.sci:
                self.write_external_links(w)
            self.write_lists(w)
            write_footer(w)

        if self.taxon_id and not (self.jpg_list or self.child):
            print(f'{self.name} is observed, but has no photos')

        if self.top_level == 'flowering plants':
            if self.jpg_list and not self.color:
                print(f'No color for flower: {self.name}')
        elif self.color:
            print(f'Color specified for non-flower: {self.name}')

    def record_genus(self):
        # record all pages that are within each genus
        sci = self.sci
        if self.level in ('genus', 'species', 'below'):
            genus = sci.split(' ')[0]
            if genus not in genus_page_list:
                genus_page_list[genus] = []
            genus_page_list[genus].append(self)
