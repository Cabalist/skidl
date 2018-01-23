# -*- coding: utf-8 -*-

# MIT license
#
# Copyright (C) 2018 by XESS Corp.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
Handles schematic libraries for various ECAD tools.
"""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import str
from future import standard_library
standard_library.install_aliases()

from .utilities import *


class SchLib(object):
    """
    A class for storing parts from a schematic component library file.

    Attributes:
        filename: The name of the file from which the parts were read.
        parts: The list of parts (composed of Part objects).

    Args:
        filename: The name of the library file.
        tool: The format of the library file (e.g., KICAD).

    Keyword Args:
        attribs: Key/value pairs of attributes to add to the library.
    """

    # Keep a dict of filenames and their associated SchLib object
    # for fast loading of libraries.
    _cache = {}

    def __init__(self, filename=None, tool=None, **attribs):
        """
        Load the parts from a library file.
        """

        import skidl

        if tool is None:
            tool = skidl.get_default_tool()

        # Library starts off empty of parts.
        self.parts = []

        # Attach attributes to the library.
        for k, v in attribs.items():
            setattr(self, k, v)

        # If no filename, create an empty library.
        if not filename:
            pass

        # Load this SchLib with an existing SchLib object if the file name
        # matches one in the cache.
        elif filename in self._cache:
            self.__dict__.update(self._cache[filename].__dict__)

        # Otherwise, load from a schematic library file.
        else:
            try:
                # Use the tool name to find the function for loading the library.
                load_func = getattr(self, '_load_sch_lib_{}'.format(tool))
            except AttributeError:
                # OK, that didn't work so well...
                logger.error('Unsupported ECAD tool library: {}.'.format(tool))
                raise Exception
            else:
                load_func(filename, skidl.lib_search_paths[tool])
                self.filename = filename
                # Cache a reference to the library.
                self._cache[filename] = self

    @classmethod
    def reset(cls):
        """Clear the cache of processed library files."""
        cls._cache = {}

    def _load_sch_lib_kicad(self, filename=None, lib_search_paths_=None):
        """
        Load the parts from a KiCad schematic library file.

        Args:
            filename: The name of the KiCad schematic library file.
        """

        import skidl
        from .defines import KICAD, LIBRARY
        from .Part import Part

        # Try to open the file. Add a .lib extension if needed. If the file
        # doesn't open, then try looking in the KiCad library directory.
        try:
            f = find_and_open_file(filename, lib_search_paths_,
                                   skidl.lib_suffixes[KICAD])
        except Exception as e:
            raise Exception(
                'Unable to open KiCad Schematic Library File {} ({})'.format(
                    filename, str(e)))

        # Check the file header to make sure it's a KiCad library.
        header = []
        header = [f.readline()]
        if header and 'EESchema-LIBRARY' not in header[0]:
            raise Exception(
                'The file {} is not a KiCad Schematic Library File.\n'.format(
                    filename))

        # Read the definition of each part line-by-line and then create
        # a Part object that gets stored in the part list.
        part_defn = []
        for line in f.readlines():

            # Skip over comments.
            if line.startswith('#'):
                pass

            # Look for the start of a part definition.
            elif line.startswith('DEF'):
                # Initialize the part definition with the first line.
                # This will also signal that succeeding lines should be added.
                part_defn = [line]

            # If gathering the part definition has begun, then continue adding lines.
            elif part_defn:
                part_defn.append(line)

                # If the current line ends this part definition, then create
                # the Part object and add it to the part list. Be sure to
                # indicate that the Part object is being added to a library
                # and not to a schematic netlist.
                if line.startswith('ENDDEF'):
                    self.add_parts(
                        Part(
                            part_defn=part_defn,
                            tool=KICAD,
                            dest=LIBRARY))

                    # Clear the part definition in preparation for the next one.
                    part_defn = []

        # Now add information from any associated DCM file.
        filename = os.path.splitext(filename)[0]  # Strip any extension.
        f = find_and_open_file(
            filename, lib_search_paths_, '.dcm', allow_failure=True)
        if not f:
            return

        part_desc = {}
        for line in f.readlines():

            # Skip over comments.
            if line.startswith('#'):
                pass

            # Look for the start of a part description.
            elif line.startswith('$CMP'):
                part_desc['name'] = line.split()[-1]

            # If gathering the part definition has begun, then continue adding lines.
            elif part_desc:
                if line.startswith('D'):
                    part_desc['description'] = ' '.join(line.split()[1:])
                elif line.startswith('K'):
                    part_desc['keywords'] = ' '.join(line.split()[1:])
                elif line.startswith('$ENDCMP'):
                    try:
                        part = self.get_part_by_name(
                            part_desc['name'], silent=True)
                    except Exception:
                        pass
                    else:
                        part.description = part_desc.get('description', '')
                        part.keywords = part_desc.get('keywords', '')
                    part_desc = {}
                else:
                    pass

    def _load_sch_lib_skidl(self, filename=None, lib_search_paths_=None):
        """
        Load the parts from a SKiDL schematic library file.

        Args:
            filename: The name of the SKiDL schematic library file.
        """

        import skidl
        from .defines import SKIDL

        try:
            f = find_and_open_file(filename, lib_search_paths_,
                                   skidl.lib_suffixes[SKIDL])
        except Exception as e:
            raise Exception(
                'Unable to open SKiDL Schematic Library File {} ({})'.format(
                    filename, str(e)))
        try:
            # The SKiDL library is stored as a Python module that's executed to
            # recreate the library object.
            vars_ = {}  # Empty dictionary for storing library object.
            exec(f.read(), vars_)  # Execute and store library in dict.

            # Now look through the dict to find the library object.
            for val in vars_.values():
                if isinstance(val, SchLib):
                    # Overwrite self with the new library.
                    self.__dict__.update(val.__dict__)
                    return

            # Oops! No library object. Something went wrong.
            raise Exception('No SchLib object found in {}'.format(filename))

        except Exception as e:
            logger.error('Problem with {}'.format(f))
            logger.error(e)
            raise

    def add_parts(self, *parts):
        """Add one or more parts to a library."""

        from .defines import TEMPLATE

        for part in flatten(parts):
            # Parts with the same name are not allowed in the library.
            # Also, do not check the backup library to see if the parts
            # are in there because that's probably a different library.
            if not self.get_parts(
                    use_backup_lib=False, name=re.escape(part.name)):
                self.parts.append(part.copy(dest=TEMPLATE))
        return self

    __iadd__ = add_parts

    def get_parts(self, use_backup_lib=True, **criteria):
        """
        Return parts from a library that match *all* the given criteria.

        Keyword Args:
            criteria: One or more keyword-argument pairs. The keyword specifies
                the attribute name while the argument contains the desired value
                of the attribute.

        Returns:
            A single Part or a list of Parts that match all the criteria.
        """

        import skidl

        parts = list_or_scalar(filter_list(self.parts, **criteria))
        if not parts and use_backup_lib and skidl.QUERY_BACKUP_LIB:
            try:
                backup_lib_ = skidl.load_backup_lib()
                parts = backup_lib_.get_parts(use_backup_lib=False, **criteria)
            except AttributeError:
                pass
        return parts

    def get_part_by_name(self, name, allow_multiples=False, silent=False):
        """
        Return a Part with the given name or alias from the part list.

        Args:
            name: The part name or alias to search for in the library.
            allow_multiples: If true, return a list of parts matching the name.
                If false, return only the first matching part and issue
                a warning if there were more than one.
            silent: If true, don't issue errors or warnings.

        Returns:
            A single Part or a list of Parts that match all the criteria.
        """

        # First check to see if there is a part or parts with a matching name.
        parts = self.get_parts(name=name)

        # No part with that name, so check for an alias that matches.
        if not parts:
            parts = self.get_parts(aliases=name)

            # No part with that alias either, so signal an error.
            if not parts:
                if not silent:
                    logger.error(
                        'Unable to find part {} in library {}.'.format(
                            name, getattr(self, 'filename', 'UNKNOWN')))
                raise Exception

        # Multiple parts with that name or alias exists, so return the list
        # of parts or just the first part on the list.
        if isinstance(parts, (list, tuple)):

            # Return the entire list if multiples are allowed.
            if allow_multiples:
                parts = [p.parse() for p in parts]

            # Just return the first part from the list if multiples are not
            # allowed and issue a warning.
            else:
                if not silent:
                    logger.warning(
                        'Found multiple parts matching {}. Selecting {}.'.
                        format(name, parts[0].name))
                parts = parts[0]
                parts.parse()

        # Only a single matching part was found, so return that.
        else:
            parts.parse()

        # Return the library part or parts that were found.
        return parts

    # Get part by name or alias using []'s.
    __getitem__ = get_part_by_name

    def __str__(self):
        """Return a list of the part names in this library as a string."""
        return '\n'.join(
            ['{}: {}'.format(p.name, p.description) for p in self.parts])

    __repr__ = __str__

    def export(self, libname, file_=None, tool=None):
        """
        Export a library into a file.

        Args:
            libname: A string containing the name of the library.
            file_: The file the library will be exported to. It can either
                be a file object or a string or None. If None, the file
                will be the same as the library name with the library
                suffix appended.
            tool: The CAD tool library format to be used. Currently, this can
                only be SKIDL.
        """

        def prettify(s):
            """Breakup and indent library export string."""
            s = re.sub(r'(Part\()', r'\n        \1', s)
            s = re.sub(r'(Pin\()', r'\n            \1', s)
            return s

        import skidl
        from .defines import SKIDL

        if tool is None:
            tool = SKIDL

        if not file_:
            file_ = libname + skidl.lib_suffixes[tool]

        export_str = 'from skidl import Pin, Part, SchLib, SKIDL, TEMPLATE\n\n'
        export_str += "SKIDL_lib_version = '0.0.1'\n\n"
        part_export_str = ','.join([p.export() for p in self.parts])
        export_str += '{} = SchLib(tool=SKIDL).add_parts(*[{}])'.format(
            cnvt_to_var_name(libname), part_export_str)
        export_str = prettify(export_str)
        with opened(file_, "w") as f:
            f.write(export_str)

    def __len__(self):
        """
        Return number of parts in library.
        """
        return len(self.parts)