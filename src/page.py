import re
import yaml
import io

# My files
from error import *
from files import *
from find_page import *
from obs import *
from easy import *
from glossary import *
from parse import *

###############################################################################

page_array = [] # array of pages; only appended to; never otherwise altered
genus_page_list = {} # genus name -> list of pages in that genus
genus_family = {} # genus name -> family name

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

ranks = ('subtribe', 'tribe', 'supertribe',
         'subfamily', 'family', 'superfamily',
         'suborder', 'order', 'superorder',
         'subclass', 'class', 'superclass',
         'subphylum', 'phylum',
         'kingdom')

trie = Trie(ranks)
ex = trie.get_pattern()
re_group = re.compile(rf'({ex}):\s*(.*?)\s*$')

group_child_set = {} # rank -> group -> set of top-level pages in group
for rank in ranks:
    group_child_set[rank] = {}

with open(root_path + '/data/family names.yaml', encoding='utf-8') as f:
    family_com = yaml.safe_load(f)

family_sci = {}
for sci, com in family_com.items():
    family_sci[com] = sci

###############################################################################

def sort_pages(page_set, color=None, with_depth=False):
    # helper function to sort by name
    def by_name(page):
        if page.com:
            if page.sci:
                # Since some pages may have the same common name, use the
                # scientific name as a tie breaker to ensure a consistent order.
                return page.com.lower() + '  ' + page.sci.lower()
            else:
                # If the page has no scientific name, then presumably it
                # doesn't share its common name with any other pages.
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
        self.group = {} # taxonomic rank -> sci name or None if conflicting
        self.group_resolved = set() # taxonomic rank if group is resolved
        self.level = None # taxonomic level: above, genus, species, or below

        self.no_sci = False # true if it's a key page for unrelated species

        self.top_level = None # 'flowering plants', 'ferns', etc.

        # Alternative scientific names
        self.elab_calflora = None
        self.elab_calphotos = None
        self.elab_jepson = None
        self.elab_inaturalist = None

        # the iNaturalist common name.
        # must be None if the common name isn't set.
        # if valid, must be different than the common name.
        self.icom = None

        self.has_child_key = False # true if at least one child gets key info
        self.autopopulated = False # true if it's an autopopulated family page

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

    def change_name_to_sci(self):
        del name_page[self.name]
        self.set_name(self.sci)

    def set_name(self, name):
        if name in name_page:
            error(f'Multiple pages created with name "{name}"')
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
            error(f'Same scientific name ({sci}) set for {sci_page[sci].name} and {self.name}')

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
        if self.top_level is None:
            self.top_level = top_level
            for child in self.child:
                child.set_top_level(top_level, tree_top)
        elif self.top_level == top_level:
            # The top level has already been set
            # (which implies that its children have had it set, too).
            return
        else:
            error(f'{self.name} is under both {self.top_level} and {top_level} ({tree_top})')

    def assign_group(self, rank, group):
        self.group[rank] = group

    def set_group(self, rank, group):
        if rank in self.group_resolved:
            # The page's group has already been set
            # (which implies that its children have had their group set, too).
            return

        if rank in self.group and group != self.group[rank]:
            error(f"{self.name} thinks it's in '{self.group[rank]}', but a parent thinks it's in {rank} {group}")

        self.group_resolved.add(rank)

        if group not in group_child_set[rank]:
            group_child_set[rank][group] = set()

        if self.sci == group:
            # This page *is* the group page, which means (for our purposes)
            # that it is not a descendent of the group, but its children
            # are.
            self.group[rank] = None
            for child in self.child:
                child.set_group(rank, group)
        else:
            self.group[rank] = group
            group_child_set[rank][group].add(self)

            # Push the group into all children, and remove those children from
            # group_child_set.
            for child in self.child:
                child.set_group(rank, group)
                group_child_set[rank][group].discard(child)

    def resolve_group(self, rank):
        if rank in self.group_resolved:
            # The page's group has already been resolved (which implies
            # that its children have had their groups resolved, too).
            return

        if rank in self.group:
            # We know the group, but haven't resolved it yet.
            # That's an easy task.
            group = self.group[rank]

            # translate a common name into the expected scientific name
            if group in family_com:
                pass # good
            elif group in family_sci:
                group = family_sci[group]
            else:
                page = find_page1(group)
                if page:
                    group = page.sci
                # If we still haven't found a record for the group anywhere,
                # they either
                # - an error will be printed when a family page is autogenerated
                #   for it, or
                # - it's a group that will never have a page.
                # Either way, we continue on with the given name, and the
                # appropriate thing will (or won't) happen later.

            # In case we changed the group name (from common to scientific),
            # record the change.
            self.group[rank] = group

            self.set_group(rank, group)
            return

        # We set 'group' as the indeterminate value instead of self.group[rank]
        # because we'll set self.group[rank] later with a call to set_group().
        # In this case, group = None means no group has been set yet.
        # If the group is found to be conflicting, we'll set self.group[rank]
        # to None and immediately exit the function.
        group = None

        # set the group of all children
        for child in self.child:
            child.resolve_group(rank)

        # if all children appear to share the same group, use that as the
        # current page's group.  But if the children have different groups,
        # set this page's group to None and immediately exit.  I.e. this
        # page's group is never None during operation of this loop.
        for child in self.child:
            if rank not in child.group:
                # The child doesn't know its group, but also isn't obviously
                # in multiple groups.  Just ignore it.
                pass
            elif child.group[rank]:
                if not group:
                    # The child has a group and this page does not.
                    group = child.group[rank]
                elif group != child.group[rank]:
                    # The child's group conflicts with previous children.
                    self.group[rank] = None
                    return
            else:
                # The child is a member of conflicting groups.
                self.group[rank] = None
                return

        if group:
            self.set_group(rank, group)

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
        elif elab.endswith(' spp.'):
            (genus, spp) = elab.split(' ')
            return f'<i>{genus}</i> spp.'
        else:
            if self.is_hybrid:
                elab = re.sub(r' ', ' &times; ', elab)
            elab = f'<i>{elab}</i>'
            elab = re.sub(r' ssp\. ', '</i> ssp. <i>', elab)
            elab = re.sub(r' var\. ', '</i> var. <i>', elab)
            return elab

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

    def parse_glossary(self):
        if re.search(r'^{([^-].*?)}', self.txt, flags=re.MULTILINE):
            if self.name in glossary_taxon_dict:
                glossary = glossary_taxon_dict[self.name]
            else:
                glossary = Glossary(self.name)
                glossary.taxon = self.name
                glossary.title = self.name
                glossary.txt = None
            self.txt = glossary.parse_terms(self.txt)

    def set_sci_alt(self, sites, elab):
        if 'f' in sites:
            self.elab_calflora = elab
        if 'p' in sites:
            self.elab_calphotos = elab
        if 'j' in sites:
            self.elab_jepson = elab
        if 'i' in sites:
            self.elab_inaturalist = elab
            isci = strip_sci(elab)
            if isci in isci_page and isci_page[isci] != self:
                error('{isci_page[isci].name} and {self.name} both use sci_i {elab}')
            isci_page[isci] = self

    def set_complete(self, matchobj):
        if matchobj.group(1) == 'x':
            if self.genus_complete is not None:
                error(f'{self.name} has both x:{self.genus_complete} and x:{matchobj.group(3)}')
            self.genus_complete = matchobj.group(3)
            if matchobj.group(2):
                self.genus_key_incomplete = True
        else:
            if self.species_complete is not None:
                error(f'{self.name} has both xx:{self.species_complete} and xx:{matchobj.group(3)}')
            self.species_complete = matchobj.group(3)
            if matchobj.group(2):
                self.species_key_incomplete = True
        return ''

    def set_colors(self, color_str):
        if self.color:
            error(f'color is defined more than once for page {self.name}')

        self.color = set([x.strip() for x in color_str.split(',')])

        # record the original order of colors in case we want to write
        # it out.
        self.color_txt = color_str

        # check for bad colors.
        for color in self.color:
            if color not in color_list:
                error(f'page {self.name} uses undefined color {color}')

    def record_ext_photo(self, label, link):
        if (label, link) in self.ext_photo_list:
            error(f'{link} is specified more than once for page {self.name}')
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
            error(f'circular loop when creating link from {self.name} to {child.name}')
        elif self in child.parent:
            error(f'{child.name} added as child of {self.name} twice')
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
                        error(f'page {self.name} has ambiguous child {com}')
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
                        error(f"page {self.name} refers to child {com}:{sci}, but the common name doesn't match")
                else:
                    child_page.set_com(com)
            if sci:
                child_page.set_sci(sci)

            # Replace the =={...} field with a simplified =={index,suffix} line.
            # This will create the appropriate link later in the parsing.
            return f'=={child_page.index}{suffix}'

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

            matchobj = re_group.match(c)
            if matchobj:
                data_object.assign_group(matchobj.group(1), matchobj.group(2))
                continue

            if c in ('', '[', ']'):
                data_object = self

            c_list.append(c)
        self.txt = '\n'.join(c_list) + '\n'

    def link_style(self):
        if self.autopopulated:
            return 'family'
        elif self.key:
            return 'parent'
        elif self.jpg_list:
            return 'leaf'
        else:
            return 'unobs'

    def create_link(self, lines):
        pageurl = url(self.name)
        return f'<a href="{pageurl}.html" class="{self.link_style()}">{self.format_full(lines)}</a>'

    def write_parents(self, w):
        c_list = []
        for parent in sort_pages(self.parent):
            if parent.has_child_key or parent.level != 'above':
                c_list.append(f'Key to {parent.create_link(1)}')
        if c_list:
            s = '<br>\n'.join(c_list)
            w.write(f'<p>\n{s}\n</p>\n')

    def page_matches_color(self, color):
        return (color is None or color in self.color)

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
            sciurl = url(sci)
            link = f'https://www.inaturalist.org/observations/chris_nelson?taxon_name={sciurl}&order_by=observed_on'
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
            sciurl = url(sci)
            add_link(elab, None, f'<a href="https://www.inaturalist.org/taxa/search?q={sciurl}&view=list" target="_blank">iNaturalist</a>')

        if self.level != 'above' or self.elab.startswith('family '):
            # CalFlora can be searched by family,
            # but not by other high-level classifications.
            elab = self.choose_elab(self.elab_calflora)
            elaburl = url(elab)
            add_link(elab, self.elab_calflora, f'<a href="https://www.calflora.org/cgi-bin/specieslist.cgi?namesoup={elaburl}" target="_blank">CalFlora</a>');

        if self.level in ('species', 'below'):
            # CalPhotos cannot be searched by high-level classifications.
            # It can be searched by genus, but I don't find that at all useful.
            elab = self.choose_elab(self.elab_calphotos)
            if self.elab not in elab:
                # CalPhotos can search for multiple names, and for cases such
                # as Erythranthe, it may have photos under both names.
                # Use both names when linking to CalPhotos, but for simplicity
                # list only the txt-specified name in the HTML listing.
                expanded_elab = self.elab + '|' + elab
            else:
                expanded_elab = elab
            elaburl = url(expanded_elab)
            # rel-taxon=begins+with -> allows matches with lower-level detail
            add_link(elab, self.elab_calphotos, f'<a href="https://calphotos.berkeley.edu/cgi/img_query?rel-taxon=begins+with&where-taxon={elaburl}" target="_blank">CalPhotos</a>');

        if self.level != 'above' or self.elab.startswith('family '):
            # Jepson can be searched by family,
            # but not by other high-level classifications.
            elab = self.choose_elab(self.elab_jepson)
            # Jepson uses "subsp." instead of "ssp.", but it also allows us to
            # search with that qualifier left out entirely.
            sci = strip_sci(elab)
            sciurl = url(sci)
            add_link(elab, self.elab_jepson, f'<a href="http://ucjeps.berkeley.edu/eflora/search_eflora.php?name={sciurl}" target="_blank">Jepson&nbsp;eFlora</a>');

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
            genusurl = url(genus)
            add_link(elab, self.elab_calflora, f'<a href="https://www.calflora.org/entry/wgh.html#srch=t&taxon={genusurl}&group=none&fmt=photo&y=37.5&x=-122&z=8&wkt=-123.1+38,-121.95+38,-121.05+36.95,-122.2+36.95,-123.1+38" target="_blank">Bay&nbsp;Area&nbsp;species</a>')

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
            w.write(f'<p>\n{txt}\n</p>\n')

    def write_lists(self, w):
        if self.top_level != 'flowering plants':
            return

        if not self.child and not self.jpg_list:
            return

        w.write('<p class="list-head">Flower lists that include this page:</p>\n')
        w.write('<ul>\n')

        for color in color_list:
            if color in self.color:
                colorurl = url(color)
                w.write(f'<li><a href="{colorurl}.html">{color} flowers</a></li>\n')

        w.write('<li><a href="flowering%20plants.html">all flowers</a></li>\n')
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
            pageurl = url(self.name)
            jpgurl = url(self.jpg_list[0])
            w.write(f'<a href="{pageurl}.html"><img src="../thumbs/{jpgurl}.jpg" alt="photo" class="list-thumb"></a>')

        w.write(f'{self.create_link(2)}</div>\n')

    def get_ancestor_set(self):
        ancestor_set = set()
        ancestor_set.add(self)
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
                if glossary != self.glossary.parent:
                    error(f'{self.name} has two different parent glossaries')
            else:
                if glossary != self.glossary:
                    error(f'{self.name} gets two different glossaries')

            # No need to continue the tree traversal through this node
            # since it and its children have already set the glossary.
            return

        if self.name in glossary_taxon_dict:
            # Set the glossary of this taxon as a child of
            # the parent glossary of this taxon.
            sub_glossary = glossary_taxon_dict[self.name]
            sub_glossary.set_parent(glossary)
            glossary = sub_glossary

        self.glossary = glossary

        for child in self.child:
            child.set_glossary(glossary)

    def parse_child_and_key(self, child_idx, suffix, text):
        child = page_array[child_idx]

        # Give the child a copy of the text from the parent's key.
        # The child can use this (pre-parsed) text if it has no text
        # of its own.
        if ((self.level == 'genus' and child.level in ('species', 'below')) or
            (self.level == 'species' and child.level == 'below') or
            not child.key_txt):
            child.key_txt = text

        if text:
            # Remember that at least one child was given key info.
            self.has_child_key = True

        link = child.create_link(2)

        name = child.name
        jpg = None
        if suffix:
            if name + suffix in jpg_files:
                jpg = name + suffix
            else:
                error(name + suffix + '.jpg not found on page ' + name)

        if not jpg:
            jpg = child.get_jpg()

        if not jpg:
            ext_photo = child.get_ext_photo()

        pageurl = url(child.name)
        if jpg:
            jpgurl = url(jpg)
            img = f'<a href="{pageurl}.html"><img src="../thumbs/{jpgurl}.jpg" alt="photo" class="page-thumb"></a>'
        elif ext_photo:
            img = f'<a href="{pageurl}.html" class="enclosed {child.link_style()}"><div class="page-thumb-text">'
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
            return '<p>' + link + '</p>\n' + text
        elif text:
            # Duplicate and contain the text link so that the following text
            # can either be below the text link and next to the image or
            # below both the image and text link, depending on the width of
            # the viewport.
            return f'<div class="flex-width"><div class="photo-box">{img}\n<span class="show-narrow">{link}</span></div><div><span class="show-wide">{link}</span>{text}</div></div>'
        else:
            return f'<div class="photo-box">{img}\n<span>{link}</span></div>'

    def parse(self):
        s = self.txt

        s = parse_txt(self.name, s, self, self.glossary)

        if not self.has_child_key:
            # No child has a key, so reduce the size of child photos.
            s = re.sub(r'class="page-thumb"', r'class="list-thumb"', s)

        self.txt = s

    def parse2(self):
        # Use the text supplied in the text file if present.
        # Otherwise use the key text from its parent.
        # If the page's text file contains only metadata (e.g.
        # scientific name or color) so that the remaining text is
        # blank, then use the key text from its parent in that case, too.
        if re.search('\S', self.txt):
            s = self.txt
        else:
            s = self.key_txt

        self.txt = parse2_txt(self.name, s, self.glossary)

    def any_parent_within_level(self, within_level_list):
        for parent in self.parent:
            if parent.level is None:
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
                w.write('<p>')
                if complete is None:
                    if top == 'genus':
                        w.write(f'<b>Caution: There may be{other} {members} of this {top} not yet included in this guide.</b>')
                    else:
                        return # Don't write the <p/> at the end
                elif complete == 'none':
                    if top == 'genus':
                        error("x:none used for " + self.name)
                    else:
                        w.write('This species has no subspecies or variants.')
                elif complete == 'uncat':
                    if top == 'genus':
                        error("x:uncat used for " + self.name)
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
                w.write('</p>\n')
            elif complete:
                if top == 'genus':
                    error(f'{self.name} uses the x: keyword but is not the top of genus')
                else:
                    error(f'{self.name} uses the xx: keyword but is not the top of species')

        with open(working_path + "/html/" + filename(self.name) + ".html",
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

            # The h1 header may include one or more regular-sized lines
            # immediately following it, and we want the vertical spacing below
            # the h1 header to be different if these lines are present.
            # Therefore, we calculate these lines before writing the h1 header,
            # but write them after it.
            c_list = []

            # List the iNaturalist common name if it's different.
            if self.icom:
                c_list.append(f'(<b>{self.icom}</b>)')

            # If the common name was listed in the <h1> header,
            # list the scientific name as a smaller line below.
            if com and elab:
                c_list.append(f'<b>{self.format_elab()}</b>')

            # If the page has autopopulated parents, list them here.
            # Parents with keys are listed more prominently below.
            # Most likely no page will have more than one autopopulated
            # parent, so I don't try to do particularly smart sorting here.
            for parent in sort_pages(self.parent):
                if not parent.has_child_key and parent.level == 'above':
                    link = parent.create_link(1)
                    c_list.append(link)

            # If the page isn't a direct child of its family page, provide
            # a link to it.  (A direct child would have been listed above
            # or will be listed further below.)  Note that the family page
            # is likely to have been autopopulated, but not necessarily.
            if 'family' in self.group and self.group['family']:
                family = self.group['family']
                family_page = sci_page[family]

                if family_page not in self.parent:
                    link = family_page.create_link(1)
                    c_list.append(link)

            write_header(w, title, h1, nospace=bool(c_list))

            if c_list:
                w.write('<br/>\n'.join(c_list) + '\n')

            self.write_parents(w)

            is_top_of_genus = self.is_top_of('genus')
            is_top_of_species = self.is_top_of('species')
            write_complete(w,
                           self.genus_complete, self.genus_key_incomplete,
                           is_top_of_genus, 'genus', 'species')
            write_complete(w,
                           self.species_complete, self.species_key_incomplete,
                           is_top_of_species, 'species', 'members')

            w.write('<hr>\n')

            if self.com == 'flowering plants':
                self.write_hierarchy(w, None)
                w.write('<hr>\n')
            else:
                if len(self.jpg_list) or len(self.ext_photo_list):
                    w.write('<div class="photo-box">\n')

                    for jpg in self.jpg_list:
                        jpgurl = url(jpg)
                        w.write(f'<a href="../photos/{jpgurl}.jpg"><img src="../thumbs/{jpgurl}.jpg" alt="photo" width="200" height="200" class="leaf-thumb"></a>\n')

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

                w.write(self.txt)

                if self.jpg_list or self.ext_photo_list or self.txt:
                    w.write('<hr>\n')

            self.write_obs(w)
            if self.sci:
                self.write_external_links(w)
            if self.level != 'above':
                self.write_lists(w)
            write_footer(w)

        if self.taxon_id and not (self.jpg_list or self.child):
            error(f'{self.name} is observed, but has no photos')

        if self.top_level == 'flowering plants':
            if self.jpg_list and not self.color:
                error(f'No color for flower: {self.name}')
        elif self.color:
            error(f'Color specified for non-flower: {self.name}')

    def record_genus(self):
        # record all pages that are within each genus
        sci = self.sci
        if self.level in ('genus', 'species', 'below'):
            genus = sci.split(' ')[0]
            if genus not in genus_page_list:
                genus_page_list[genus] = []
            genus_page_list[genus].append(self)

    def write_hierarchy(self, w, color):
        # We write out the matches to a string first so that we can get
        # the total number of keys and flowers in the list (including children).
        s = io.StringIO()
        list_matches(s, self.child, False, color, set())

        obs = Obs(color)
        self.count_matching_obs(obs)
        obs.write_page_counts(w)
        w.write(s.getvalue())

# Find all flowers that match the specified color.
# Also find all pages that include *multiple* child pages that match.
# If a parent includes multiple matching child pages, those child pages are
# listed only under the parent and not individually.
# If a parent includes only one matching child page, that child page is
# listed individually, and the parent is not listed.
#
# If color is None, every page matches.
def find_matches(page_subset, color):
    match_list = []
    for page in page_subset:
        child_subset = find_matches(page.child, color)
        if len(child_subset) == 1 and color is not None:
            match_list.extend(child_subset)
        elif child_subset:
            match_list.append(page)
            if color is not None:
                # Record this container page's newly discovered color.
                page.color.add(color)
        elif page.jpg_list and page.page_matches_color(color):
            # only include the page on the list if it is a key or observed
            # flower (not an unobserved flower).
            match_list.append(page)
    return match_list

# match_set can be either a set or list of pages.
# If indent is False, we'll sort them into a list by reverse order of
# observation counts.  If indent is True, match_set must be a list, and
# its order is retained.
def list_matches(w, match_set, indent, color, seen_set):
    if indent:
        # We're under a parent with an ordered child list.  Retain its order.
        match_list = match_set
    else:
        # We're at the top level, so sort to put common pages first.
        match_list = sort_pages(match_set, color=color)

    for page in match_list:
        child_matches = find_matches(page.child, color)
        if child_matches:
            page.list_page(w, indent, child_matches)
            list_matches(w, child_matches, True, color, seen_set)
            w.write('</div>\n')
        else:
            page.list_page(w, indent, None)

        seen_set.add(page)
