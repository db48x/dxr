#!/usr/bin/env python2.6

import os
import dxr
import cgi
import itertools

class HtmlBuilder:
  def _zipper(self, func):
    """ Returns all contents from all plugins. """
    if func not in self.resmap:
      return []
    return itertools.chain(*[f(self.blob[name], self.filepath, self.tree)
      for name, f in self.resmap[func]])

  def __init__(self, tree, filepath, dstpath, blob, resmap):
    # Read and expand all templates
    self.html_header = tree.getTemplateFile("dxr-header.html")
    self.html_footer = tree.getTemplateFile("dxr-footer.html")
    self.html_sidebar_header = tree.getTemplateFile("dxr-sidebar-header.html")
    self.html_sidebar_footer = tree.getTemplateFile("dxr-sidebar-footer.html")
    self.html_main_header = tree.getTemplateFile("dxr-main-header.html")
    self.html_main_footer = tree.getTemplateFile("dxr-main-footer.html")
    
    self.source = dxr.readFile(filepath)
    self.virtroot = tree.virtroot
    self.treename = tree.tree
    self.filename = os.path.basename(filepath)
    self.filepath = filepath
    self.srcroot = tree.sourcedir
    self.dstpath = os.path.normpath(dstpath)
    self.srcpath = filepath.replace(self.srcroot + '/', '')

    self.blob = blob
    self.resmap = resmap
    self.tree = tree

    # Config info used by dxr.js
    self.globalScript = ['var virtroot = "%s", tree = "%s";' % (self.virtroot, self.treename)]

  def _buildFullPath(self, ending, includeTreename=True):
    if includeTreename:
      return os.path.join(self.virtroot, self.treename, ending) 
    else:
      return os.path.join(self.virtroot, ending) 

  def toHTML(self):
    out = open(self.dstpath, 'w')
    out.write(self.html_header + '\n')
    self.writeSidebar(out)
    self.writeMainContent(out)
    self.writeGlobalScript(out)
    out.write(self.html_footer + '\n')
    out.close()

  def writeSidebar(self, out):
    sidebarElements = [x for x in self._zipper("get_sidebar_links")]
    if len(sidebarElements) == 0: return

    out.write(self.html_sidebar_header + '\n')
    self.writeSidebarBody(out, sidebarElements)
    out.write(self.html_sidebar_footer + '\n')

  def writeSidebarBody(self, out, elements):
    containers = {}
    for e in elements:
      containers.setdefault(len(e) > 4 and e[4] or None, []).append(e)

    # Sort the containers by their location
    # Global scope goes last, and scopes declared outside of this file goes
    # before everything else
    clocs = { None: 2 ** 32 }
    for e in elements:
      if e[0] in containers:
        clocs[e[0]] = int(e[1])
    contKeys = containers.keys()
    contKeys.sort(lambda x, y: cmp(clocs.get(x, 0), clocs.get(y, 0)))

    for cont in contKeys:
      if cont is not None:
        out.write('<b>%s</b>\n<div>\n' % cgi.escape(str(cont)))
      containers[cont].sort(lambda x, y: int(x[1]) - int(y[1]))
      for e in containers[cont]:
        img = len(e) > 3 and e[3] or "images/icons/page_white_code.png"
        title = len(e) > 2 and e[2] or e[0]
        img = self._buildFullPath(img)
        out.write('<img src="%s/%s" class="sidebarimage">' % (self.virtroot, img))
        out.write('<a class="sidebarlink" title="%s" href="#l%d">%s</a><br>\n' %
          (cgi.escape(title), int(e[1]), cgi.escape(e[0])))
      if cont is not None:
        out.write('</div><br />\n')

  def writeMainContent(self, out):
    out.write(self.html_main_header)
    self.writeMainBody(out)
    out.write(self.html_main_footer)

  def writeMainBody(self, out):
    syntax_regions = self._zipper("get_syntax_regions")
    links = self._zipper("get_link_regions")
    lines = self._zipper("get_line_annotations")

    # Split up the entire source, and annotate each char invidually
    line_markers = [0]
    closure = ['', 0]
    def handle_char(x):
      if x == '\n':
        line_markers.append(closure[1])
      elif closure[0] == '\r':
        line_markers.append(closure[1] - 1)
      closure[0] = x
      closure[1] += 1
      if x == '\r' or x == '\n': return ''
      return cgi.escape(x)
    chars = [handle_char(x) for x in self.source]
    chars.append('')

    def off(val):
      if isinstance(val, tuple):
        return line_markers[val[0] - 1] + val[1]
      return val
    for syn in syntax_regions:
      chars[off(syn[0])] = '<span class="%s">%s' % (syn[2], chars[off(syn[0])])
      chars[off(syn[1]) - 1] += '</span>'
    for link in links:
      chars[off(link[0])] = '<a aria-haspopup="true" %s>%s' % (
        ' '.join([attr + '="' + str(link[2][attr]) + '"' for attr in link[2]]),
        chars[off(link[0])])
      chars[off(link[1]) - 1] += '</a>'

    # the hack is that we need the first and end to work better
    # The last "char" is the place holder for the first line entry
    line_markers[0] = -1
    # Line attributes
    for l in lines:
      chars[line_markers[l[0] - 1]] = \
        ' '.join([attr + '="' + str(l[1][attr]) + '"' for attr in l[1]])
    line_num = 2 # First line is special
    for ind in line_markers[1:]:
      chars[ind] = '</div><div %s id="l%d"><a class="ln" href="l%d">%d</a>' % \
        (chars[ind], line_num, line_num, line_num)
      line_num += 1
    out.write('<div %s id="l1"><a class="ln" href="l1">1</a>' % chars[-1])
    chars[-1] = '</div>'
    out.write(''.join(chars))

  def writeGlobalScript(self, out):
    """ Write any extra JS for the page. Lines of script are stored in self.globalScript."""
    # Add app config info
    out.write('<script type="text/javascript">')
    out.write('\n'.join(self.globalScript))
    out.write('</script>')


# HTML-ifier map
# The keys are the endings of files to match
# First set of values are {funcname, [funclist]} dicts
# funclist is the lists of functions to apply, as a (plugin name, func) tuple

htmlifier_map = {}
ending_iterator = []
def build_htmlifier_map(plugins):
  def add_to_map(ending, hmap, pluginname, append):
    for x in ['get_sidebar_links', 'get_link_regions', 'get_line_annotations',
        'get_syntax_regions']:
      details = htmlifier_map[ending].setdefault(x, [None])
      if append:
        details.append((pluginname, hmap[x]))
      else:
        details[0] = (pluginname, hmap[x])
  # Add/append details for each map
  for plug in plugins:
    plug_map = plug.get_htmlifiers()
    nosquash = 'no-override' in plug_map
    for ending in plug_map:
      if ending not in htmlifier_map:
        ending_iterator.append(ending)
        htmlifier_map[ending] = {}
      add_to_map(ending, plug_map[ending], plug.__name__, nosquash)
  # Sort the endings by maximum length, so that we can just find the first one
  # in the list
  ending_iterator.sort(lambda x, y: cmp(len(y), len(x)))

def make_html(srcpath, dstfile, treecfg, blob):
  # Match the file in srcpath
  result_map = {}
  signalStop = False
  for end in ending_iterator:
    if srcpath.endswith(end):
      for func in htmlifier_map[end]:
        reslist = result_map.setdefault(func, [None])
        flist = htmlifier_map[end][func]
        reslist.extend(flist[1:])
        if flist[0] is not None:
          reslist[0] = flist[0]
          signalStop = True
    if signalStop:
      break
  builder = HtmlBuilder(treecfg, srcpath, dstfile, blob, result_map)
  builder.toHTML()