"""An extensible ASCII table reader and writer.

daophot.py:
  Classes to read DAOphot table format

:Copyright: Smithsonian Astrophysical Observatory (2011)
:Author: Tom Aldcroft (aldcroft@head.cfa.harvard.edu)
"""

## 
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions are met:
##     * Redistributions of source code must retain the above copyright
##       notice, this list of conditions and the following disclaimer.
##     * Redistributions in binary form must reproduce the above copyright
##       notice, this list of conditions and the following disclaimer in the
##       documentation and/or other materials provided with the distribution.
##     * Neither the name of the Smithsonian Astrophysical Observatory nor the
##       names of its contributors may be used to endorse or promote products
##       derived from this software without specific prior written permission.
## 
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
## ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
## WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
## DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
## DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
## (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
## ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
## (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS  
## SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import re
import numpy as np
from . import core
from . import basic
from . import fixedwidth
from ...utils import OrderedDict

class Daophot(core.BaseReader):
    """Read a DAOphot file.
    Example::

      #K MERGERAD   = INDEF                   scaleunit  %-23.7g  
      #K IRAF = NOAO/IRAFV2.10EXPORT version %-23s
      #K USER = davis name %-23s
      #K HOST = tucana computer %-23s
      #
      #N ID    XCENTER   YCENTER   MAG         MERR          MSKY           NITER    \\
      #U ##    pixels    pixels    magnitudes  magnitudes    counts         ##       \\
      #F %-9d  %-10.3f   %-10.3f   %-12.3f     %-14.3f       %-15.7g        %-6d     
      #
      #N         SHARPNESS   CHI         PIER  PERROR                                \\
      #U         ##          ##          ##    perrors                               \\
      #F         %-23.3f     %-12.3f     %-6d  %-13s
      #
      14       138.538   256.405   15.461      0.003         34.85955       4        \\
      -0.032      0.802       0     No_error

    The keywords defined in the #K records are available via output table
    ``meta`` attribute::

      data = ascii.read('t/daophot.dat')
      for keyword in data.meta['keywords']:
          print keyword['name'], keyword['value'], keyword['units'], keyword['format']

    The units and formats are available in the output table columns::

      for colname in data.colnames:
           col = data[colname]
           print colname, col.units, col.format
    """

    def __init__(self):
        core.BaseReader.__init__(self)
        self.header = DaophotHeader()
        self.inputter = core.ContinuationLinesInputter()
        self.inputter.no_continue = r'\s*#'
        self.data.splitter = fixedwidth.FixedWidthSplitter()
        self.data.start_line = 0
        self.data.comment = r'\s*#'

    def read(self, table):
        out = core.BaseReader.read(self, table)

        # Read keywords as a table embedded in the header comments
        if len(self.comment_lines) > 0:
            names = ('temp1', 'name', 'temp2', 'value', 'units', 'format')
            reader = core._get_reader(Reader=basic.NoHeader, comment=r'(?!#K)', names=names)
            headerkeywords = reader.read(self.comment_lines)

            out.meta['keywords'] = OrderedDict()
            for headerkeyword in headerkeywords:
                keyword_dict = dict((x, headerkeyword[x]) for x in ('value', 'units', 'format'))
                out.meta['keywords'][headerkeyword['name']] = keyword_dict
        self.cols = self.header.cols

        return out

    def write(self, table=None):
        raise NotImplementedError


class DaophotHeader(core.BaseHeader):
    """Read the header from a file produced by the IRAF DAOphot routine."""
    def __init__(self):
        core.BaseHeader.__init__(self)
        self.comment = r'\s*#K'

    def get_cols(self, lines):
        """Initialize the header Column objects from the table ``lines`` for a DAOphot
        header.  The DAOphot header is specialized so that we just copy the entire BaseHeader
        get_cols routine and modify as needed.

        :param lines: list of table lines
        :returns: list of table Columns
        """

        # Parse a series of column defintion lines like below.  There may be several
        # such blocks in a single file (where continuation characters have already been
        # stripped).
        # #N ID    XCENTER   YCENTER   MAG         MERR          MSKY           NITER    
        # #U ##    pixels    pixels    magnitudes  magnitudes    counts         ##       
        # #F %-9d  %-10.3f   %-10.3f   %-12.3f     %-14.3f       %-15.7g        %-6d     
        coldef_lines = ['', '', '']
        starts = ('#N ', '#U ', '#F ')
        col_width = []
        col_len_def = re.compile(r'[0-9]+')
        re_colformat_def = re.compile(r'#F([^#]+)')
        for line in lines:
            if not line.startswith('#'):
                break # End of header lines
            else:
                formatmatch = re_colformat_def.search(line)
                if formatmatch:
                    form = formatmatch.group(1).split()
                    width = ([int(col_len_def.search(s).group()) for s in form])
                    # original data format might be shorter than 80 characters
                    # and filled with spaces
                    width[-1] = 80 - sum(width[:-1])
                    col_width.extend(width)
                for i, start in enumerate(starts):
                    if line.startswith(start):
                        line_stripped = line[2:]
                        coldef_lines[i] = coldef_lines[i] + line_stripped
                        break
        
        # At this point colddef_lines has three lines corresponding to column
        # names, units, and format.  Get the column names by splitting the
        # first line on whitespace.
        self.names = coldef_lines[0].split()
        if not self.names:
            raise core.InconsistentTableError('No column names found in DAOphot header')

        ends = np.cumsum(col_width)
        starts = ends - col_width

        # If there wasn't a #U defined (not sure of DAOphot specification), then
        # replace the empty line with the right number of ## indicators, which matches
        # the DAOphot "no unit" tag.
        for i, coldef_line in enumerate(coldef_lines):
            if not coldef_line:
                coldef_lines[i] = '## ' * len(self.names)

        # Read the three lines as a basic table.
        reader = core._get_reader(Reader=basic.Basic, comment=None)
        reader.header.comment = None
        coldefs = reader.read(coldef_lines)

        # Create the list of io.ascii column objects
        self._set_cols_from_names()

        # Set units and format as needed.
        for col in self.cols:
            if coldefs[col.name][0] != '##':
                col.units = coldefs[col.name][0]
            if coldefs[col.name][1] != '##':
                col.format = coldefs[col.name][1]

        # Set column start and end positions.  Also re-index the cols because
        # the FixedWidthSplitter does NOT return the ignored cols (as is the
        # case for typical delimiter-based splitters)
        for i, col in enumerate(self.cols):
            col.start = starts[col.index]
            col.end = ends[col.index]
            col.index = i
        
        self.n_data_cols = len(self.cols)