"use strict";

var ac_is_hidden = true;
function expose_ac() {
  e_autocomplete_box.style.display = 'block';
  ac_is_hidden = false;
}

function hide_ac() {
  e_autocomplete_box.style.display = 'none';
  ac_is_hidden = true;
}

function fn_focusin() {
  if (ac_is_hidden) {
    /* e_search_input.select(); */ /* Not as smooth on Android as desired. */
    fn_search();
  }
}

function fn_focusout() {
  if (!ac_is_hidden) {
    hide_ac();
  }
}

function fn_search_box_focusout(event) {
  if (event.target == this) {
    fn_focusout()
  }
}

/* When comparing names, ignore all non-letter characters and ignore case. */
function compress(name) {
  return name.toUpperCase().replace(/\W/g, '');
}

/* Find the position of the Nth letter in string 'str',
where N = cmp_match_pos + len, with adjustments as follows:
- If len is 0, we're looking for the position just before the (N+1)th letter.
- Otherwise, we're looking for the position just after the Nth letter. */
function find_letter_pos(str, cmp_match_pos, len) {
  var regex = /\w/g;
  var n = cmp_match_pos + len;
  if (len == 0) n++

  for (var i = 0; i < n; i++) {
    regex.test(str);
  }
  if (len == 0) {
    return regex.lastIndex - 1;
  } else {
    return regex.lastIndex;
  }
}

function index_of_letter(str, letter_num) {
  var letter_cnt = 0;
  for (var i = 0; letter_cnt < letter_num; i++) {
    if (str.substring(i).search(/^\w/) >= 0) {
      letter_cnt++;
    }
  }

  return i;
}

/* check() is called multiple times, once for each name associated with a page.
   Throughout this process, it accumulates the best fit in the best_fit_info
   structure.  An exact match is given highest priority.  A match at the start
   of the name has medium priority, and a match somewhere later in the name
   has the lowest priority. */
function check(search_str_cmp, match_str, page_info, best_fit_info, pri_adj) {
  var cx = compress(match_str);
  var pri = 0;
  if (cx.includes(search_str_cmp)) {
    pri = 13;
    if (cx.startsWith(search_str_cmp)) {
      pri = 13.2;
      if (cx == search_str_cmp) {
        pri = 14;
      }
    }
  }
  if (pri) {
    /* Reduce the priority of an autogenerated page to below all others. */
    if ((page_info.x == 'f') || (page_info.x == 'u')) {
      pri -= 2.0;
    } else if ((page_info.x == 'g') || (page_info.x == 'j')) {
      pri -= 10.0;
    }

    /* Bump the priority by 0.4 if the match begins at a word boundary. */
    /* I no longer bump the priority if the match ends at a word boundary
       because that can cause priority to shift when typing the next letter
       of what the user thinks is the highest priority match. */
    var cmp_pos = cx.indexOf(search_str_cmp);
    var uncmp_start = find_letter_pos(match_str, cmp_pos, 0);
    if ((uncmp_start == 0) ||
        (/^\W/.test(match_str.substring(uncmp_start-1)))){
      pri += 0.4;
    }

    pri += pri_adj
    if (best_fit_info.pri < pri) {
      best_fit_info.pri = pri;
      best_fit_info.page_info = page_info;
    }
  }
}

function check_elab(search_str_cmp, elab, page_info, best_fit_info, pri_adj) {
  check(search_str_cmp, elab, page_info, best_fit_info, pri_adj)

  /* If the scientific name includes a subtype specifier, also check for
     a match with the specifier removed. */
  var elab_split = elab.split(' ');
  if (elab_split.length == 4) {
    var sci = elab_split[0] + ' ' + elab_split[1] + ' ' + elab_split[3]
    check(search_str_cmp, sci, page_info, best_fit_info, pri_adj)
  }
}

function startsUpper(name) {
  return (name.search(/^[A-Z]/) >= 0);
}

function hasUpper(name) {
  return (name.search(/[A-Z]/) >= 0);
}

function bold(search_str_cmp, name) {
  var has_ssp = false;
  var test_name = name;

  var name_cmp = compress(name);
  var cmp_match_pos = name_cmp.indexOf(search_str_cmp);
  if ((cmp_match_pos == -1) && startsUpper(name)) {
    /* There wasn't a match, but since it's a scientific name, maybe there
       will be a match when we take the subtype specifier out. */
    var name_split = name.split(' ');
    if (name_split.length == 4) {
      has_ssp = true;
      var ssp = name_split[2];
      var ssp_pos = name_split[0].length + 1 + name_split[1].length;
      test_name = name_split[0] + ' ' + name_split[1] + ' ' + name_split[3]
      name_cmp = compress(test_name);
      cmp_match_pos = name_cmp.indexOf(search_str_cmp);
    }
  }
  if (cmp_match_pos == -1) {
    return name;
  }

  var uncmp_match_begin = find_letter_pos(test_name,
                                          cmp_match_pos,
                                          0);
  var uncmp_match_end = find_letter_pos(test_name,
                                        cmp_match_pos,
                                        search_str_cmp.length);

  if (has_ssp) {
    if (uncmp_match_begin > ssp_pos) {
      uncmp_match_begin += ssp.length + 1;
    }
    if (uncmp_match_end > ssp_pos) {
      uncmp_match_end += ssp.length + 1;
    }
  }

  var highlighted_name = name.substring(0, uncmp_match_begin);
  highlighted_name += ('<span class="match">' +
                       name.substring(uncmp_match_begin, uncmp_match_end) +
                       '</span>');
  highlighted_name += name.substring(uncmp_match_end);

  return highlighted_name;
}

/* Get the relative path to a page. */
function fn_url(page_info) {
  if (page_info.x == 'j') {
    return 'https://ucjeps.berkeley.edu/eflora/glossary.html#' + page_info.anchor;
  } else if (page_info.x == 'g') {
    return path + page_info.page + '.html#' + page_info.anchor;
  } else {
    return path + page_info.page + '.html';
  }
}

/* Construct all the contents of a link to a page. */
function fn_link(page_info) {
  if (page_info.x == 'f') {
    var c = 'family';
  } else if (page_info.x == 'k') {
    var c = 'parent';
  } else if (page_info.x == 'o') {
    var c = 'leaf';
  } else if (page_info.x == 'g') {
    var c = 'glossary';
  } else if (page_info.x == 'j') {
    var c = 'jepson';
  } else {
    var c = 'unobs';
  }

  var target = '';
  var url = fn_url(page_info);

  /* I tried this and didn't like it.  If I ever choose to use it, I also
     have to change the behavior of the return key (where fn_url is used). */
  /*if (page_info.x == 'j') {
    target = ' target="_blank"';
  }*/

  return 'class="enclosed ' + c + '"' + target + ' href="' + url + '"'
}

/* Update the autocomplete list.
   If 'enter' is true, then navigate to the top autocompletion's page. */
function fn_search(enter) {
  var search_str_cmp = compress(e_search_input.value);

  if (search_str_cmp == '') {
    hide_ac();
    return;
  }

  /* Iterate over all pages and accumulate a list of the best matches
     against the search value. */
  var best_list = [];
  for (var i = 0; i < pages.length; i++) {
    var page_info = pages[i];
    var best_fit_info = {
      pri: 0 /* 0 means no match */
    }

    if ('com' in page_info) {
      for (var j = 0; j < page_info.com.length; j++) {
        var pri_adj = 0.0
        if (j > 0) {
          /* Secondary names have slightly reduced priority.  E.g. a species
             that used to share a name with another species can be found with
             that old name, but the species that currently uses the name
             is always the better match. */
          pri_adj = -0.1
        }
        check(search_str_cmp, page_info.com[j], page_info, best_fit_info,
              pri_adj)
      }
    }
    if ('sci' in page_info) {
      for (var j = 0; j < page_info.sci.length; j++) {
        var pri_adj = 0.0
        if (j > 0) {
          pri_adj = -0.1
        }
        check_elab(search_str_cmp, page_info.sci[j], page_info, best_fit_info,
                   pri_adj)
      }
    }

    /* If there's a match, and
       - we don't already have 10 matches or
       - the new match is better than the last match on the list
       then remember the new match. */
    if (best_fit_info.pri &&
        ((best_list.length < 10) || (best_fit_info.pri > best_list[9].pri))) {
      /* Insert the new match into the list in priority order.  In case of
         a tie, the new match goes lower on the list. */
      for (var j = 0; j < best_list.length; j++) {
        if (best_fit_info.pri > best_list[j].pri) break;
      }
      best_list.splice(j, 0, best_fit_info);
      /* If the list was already the maximum length, it is now longer than the
         maximum length.  Cut off the last entry. */
      if (best_list.length > 10) {
        best_list.splice(-1, 1);
      }
    }
  }

  if (best_list.length) {
    var ac_list = [];
    for (var i = 0; i < best_list.length; i++) {
      var page_info = best_list[i].page_info;

      if ('com' in page_info) {
        for (var j = 0; j < page_info.com.length; j++) {
          var com_bold = bold(search_str_cmp, page_info.com[j])
          if (com_bold != page_info.com[j]) {
            /* bolding has happened */
            break
          } else {
            /* default value (only used if no entry gets bolded) */
            com_bold = page_info.com[0]
          }
        }
      } else {
        com_bold = null
      }

      if ('sci' in page_info) {
        for (var j = 0; j < page_info.sci.length; j++) {
          var elab = page_info.sci[j]
          var elab_bold = bold(search_str_cmp, elab)
          if (elab_bold != elab) {
            /* bolding has happened */
            break
          } else {
            /* default value (only used if no entry gets bolded) */
            elab = page_info.sci[0]
            elab_bold = elab
          }
        }

        if (startsUpper(elab)) {
          var elab_bold_ital = '<i>' + elab_bold + '</i>';
        } else {
          /* Don't italicize the group type (e.g. "family"). */
          /* elab_bold might include a <span ...> tag for highlighting, and
             we don't want to accidentially trigger on that space.  So we
             have to carefully check whether the highlighted span starts
             before or after the space. */
          /* Note that this fails if there isn't a space.  We expect any
             elab that doesn't start with uppercase has at least two words. */
          var space_pos = elab.indexOf(' ');
          if (!elab_bold.startsWith(elab.substring(0, space_pos+1))) {
            /* The highlighted span starts before the space, so search
               backward to find the space instead.  (If the highlighed span
               spans the space, we'll end up with <i> inside the span and
               </i> outside the span, but that's OK. */
            var space_pos = elab_bold.lastIndexOf(' ');
          }
          var elab_bold_ital = (elab_bold.substring(0, space_pos) + ' <i>' +
                                elab_bold.substring(space_pos+1) + '</i>');
        }
        if (com_bold) {
          var full = com_bold + ' (' + elab_bold_ital + ')';
        } else {
          var full = elab_bold_ital;
        }
      } else {
        var full = com_bold
      }
      full = full.replace(/'/g, '&rsquo;')
      var entry = ('<p class="nogap"><a ' + fn_link(page_info) + '>' +
                   full + '</a></p>');

      /* Highlight the first entry in bold.  This entry is selected if the
         user presses 'enter'. */
      if (i == 0) {
        entry = '<b>' + entry + '</b>';
      }
      ac_list.push(entry);
    }
    e_autocomplete_box.innerHTML = ac_list.join('');
  } else {
    e_autocomplete_box.innerHTML = 'No matches found.';
  }
  expose_ac();
  if (enter && best_list.length) {
    var page_info = best_list[0].page_info
    window.location.href = fn_url(page_info);
    /* A search of the glossary from a glossary page might result in no
       page change, and so the search will remain active.  That's not
       what we want, so in that case, clear the search. */
    e_search_input.value = ''
    fn_focusout()
  }
}

/* Handle all changes to the search value.  This includes changes that
   are not accompanied by a keyup event, such as a mouse-based paste event. */
function fn_change() {
  fn_search(false);
}

/* Handle when the user presses the 'enter' key. */
function fn_keyup() {
  if (event.keyCode == 13) {
    fn_search(true);
  }
}

/* normalize the data in the pages array. */
for (var i = 0; i < pages.length; i++) {
  var page_info = pages[i]
  if ((page_info.x == 'g') || (page_info.x == 'j')) {
    if (page_info.x == 'j') {
      page_info.page = 'Jepson eFlora glossary';
    } else {
      page_info.page = glossaries[page_info.idx];
    }
    if (!('anchor' in page_info)) {
      page_info.anchor = page_info.com[0]
    }
    for (var j = 0; j < page_info.com.length; j++) {
      page_info.com[j] = page_info.com[j] + ' (' + page_info.page + ')'
    }
  } else {
    if (!('com' in page_info)) {
      if (!hasUpper(page_info.page)) {
        page_info.com = [page_info.page]
      }
    }
    if (!('sci' in page_info)) {
      if (hasUpper(page_info.page)) {
        page_info.sci = [page_info.page]
      }
    }
  }
}

/* Determine whether to add 'html/' to the URL when navigating to a page. */
if (window.location.pathname.includes('/html/')) {
  var path = '';
} else {
  var path = 'html/';
}

/* The 'body' div is everything on the page not associated with the search bar.
   Thus, clicking somewhere other than the search bar or autocomplete box
   causes the autocomplete box to be hidden. */
var e_body = document.getElementById('body');

e_body.insertAdjacentHTML('beforebegin', `
<div id="search-bg"></div>
<div id="search-container">
<input type="text" id="search" autocapitalize="none" autocorrect="off" autocomplete="off" spellcheck="false" placeholder="search for a flower or glossary term...">
<div id="autocomplete-box"></div>
</div>
`);

var e_search_input = document.getElementById('search');
e_search_input.addEventListener('input', fn_change);
e_search_input.addEventListener('keyup', fn_keyup);
e_search_input.addEventListener('focusin', fn_focusin);

var e_search_box = document.getElementById('search-container');
e_search_box.addEventListener('mousedown', fn_search_box_focusout, true);

e_body.addEventListener('mousedown', fn_focusout);

var e_autocomplete_box = document.getElementById('autocomplete-box');

/* On Android Firefox, if the user clicks an autocomplete link to navigate
   away, then hits the back button to return to the page, the search field
   is cleared (good), but the autocomplete box remains visible and populated
   (bad).  This code fixes that. */
window.onbeforeunload = fn_focusout;

/*****************************************************************************/
/* non-search functions also used by the BAWG HTML */

function fn_details(e) {
  if (e.textContent == '[show details]') {
    e.textContent = '[hide details]';
    document.getElementById('details').style.display = 'block';
  } else {
    e.textContent = '[show details]';
    document.getElementById('details').style.display = 'none';
  }
}
