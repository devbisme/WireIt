from pcbnew import *

import sys
import os
import os.path
import re
import wx
import wx.aui
import wx.lib.filebrowsebutton as FBB

WIDGET_SPACING = 5


def debug_dialog(msg):
    dlg = wx.MessageDialog(None, msg, '', wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


class DnDFilePickerCtrl(FBB.FileBrowseButtonWithHistory, wx.FileDropTarget):
    '''File browser that keeps its history.'''

    def __init__(self, *args, **kwargs):
        FBB.FileBrowseButtonWithHistory.__init__(self, *args, **kwargs)
        wx.FileDropTarget.__init__(self)
        self.SetDropTarget(self)
        self.SetDefaultAction(
            wx.DragCopy)  # Show '+' icon when hovering over this field.

    def GetPath(self, addToHistory=False):
        current_value = self.GetValue()
        if addToHistory:
            self.AddToHistory(current_value)
        return current_value

    def AddToHistory(self, value):
        if value == u'':
            return
        if type(value) in (str, unicode):
            history = self.GetHistory()
            history.insert(0, value)
            history = tuple(set(history))
            self.SetHistory(history, 0)
            self.SetValue(value)
        elif type(value) in (list, tuple):
            for v in value:
                self.AddToHistory(v)

    def SetPath(self, path):
        self.AddToHistory(path)
        self.SetValue(path)

    def OnChanged(self, evt):
        wx.PostEvent(self,
                     wx.PyCommandEvent(wx.EVT_FILEPICKER_CHANGED.typeId,
                                       self.GetId()))

    def OnDropFiles(self, x, y, filenames):
        self.AddToHistory(filenames)
        wx.PostEvent(self,
                     wx.PyCommandEvent(wx.EVT_FILEPICKER_CHANGED.typeId,
                                       self.GetId()))


class LabelledTextCtrl(wx.BoxSizer):
    '''Text-entry box with a label.'''

    def __init__(self, parent, label, value, tooltip=''):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)
        self.lbl = wx.StaticText(parent=parent, label=label)
        self.ctrl = wx.TextCtrl(
            parent=parent, value=value, style=wx.TE_PROCESS_ENTER)
        self.ctrl.SetToolTip(wx.ToolTip(tooltip))
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbl, 0, wx.ALL | wx.ALIGN_CENTER)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.ctrl, 1, wx.ALL | wx.EXPAND)
        self.AddSpacer(WIDGET_SPACING)


class LabelledListBox(wx.BoxSizer):
    '''ListBox with label.'''

    def __init__(self, parent, label, choices, tooltip=''):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)
        self.lbl = wx.StaticText(parent=parent, label=label)
        self.lbx = wx.ListBox(
            parent=parent,
            choices=choices,
            style=wx.LB_EXTENDED | wx.LB_NEEDED_SB | wx.LB_SORT,
            size=wx.Size(1, 50))
        self.lbx.SetToolTip(wx.ToolTip(tooltip))
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbl, 0, wx.ALL | wx.ALIGN_TOP)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbx, 1, wx.ALL | wx.EXPAND)
        self.AddSpacer(WIDGET_SPACING)


class Part(object):
    '''Object for storing part symbol data.'''
    pass


class Pin(object):
    '''Object for storing pin data.'''
    pass


def get_parts_from_netlist(netlist_file):
    '''Get part information from a netlist file.'''

    # Get the local and global files that contain the symbol tables.
    # Place the global file first so its entries will be overridden by any
    # matching entries in the local file.
    sym_lib_tbl_files = []  # Store the symbol table file paths here.
    brd_file = GetBoard().GetFileName()
    brd_dir = os.path.abspath(os.path.dirname(brd_file))
    brd_name = os.path.splitext(os.path.basename(brd_file))[0]
    if sys.platform == 'win32':
        default_home = os.path.expanduser(r'~\AppData\Roaming\kicad')
    else:
        default_home = os.path.expanduser(r'~/.config/kicad')
    dirs = [os.environ.get('KICAD_CONFIG_HOME', default_home), brd_dir]
    for dir in dirs:
        sym_lib_tbl_file = os.path.join(dir, 'sym-lib-table')
        if os.path.isfile(sym_lib_tbl_file):
            sym_lib_tbl_files.append(sym_lib_tbl_file)

    # Regular expression for getting the symbol library name and file location
    # from the symbol table file.
    sym_tbl_re = '\(\s*lib\s+\(\s*name\s+([^)]+)\s*\).*\(\s*uri\s+([^)]+)\s*\)'

    # Process the global and local symbol library tables to create a dict
    # of the symbol library names and their file locations.
    sym_lib_files = {}
    for tbl_file in sym_lib_tbl_files:
        with open(tbl_file, 'r') as fp:
            for line in fp:
                srch_result = re.search(sym_tbl_re, line)
                if srch_result:
                    lib_name, lib_uri = srch_result.group(1, 2)
                    sym_lib_files[lib_name.lower()] = os.path.expandvars(
                        lib_uri)

    # Add any cache or rescue libraries in the PCB directory.
    for lib_type in ['-cache', '-rescue']:
        lib_name = brd_name + lib_type
        file_name = os.path.join(brd_dir, lib_name + '.lib')
        if os.path.isfile(file_name):
            sym_lib_files[lib_name.lower()] = file_name

    # Regular expressions for getting the part reference and symbol library
    # from the netlist file.
    comp_ref_re = '\(\s*comp\s+\(\s*ref\s+([_A-Za-z][_A-Za-z0-9]*)\s*\)'
    comp_lib_re = '\(\s*libsource\s+\(\s*lib\s+([^)]+)\s*\)\s+\(\s*part\s+([^)]+)\s*\)\s*\)'

    # Scan through the netlist searching for the part references and libraries.
    parts = {}
    with open(netlist_file, 'r') as fp:
        for line in fp:

            # Search for part reference.
            srch_result = re.search(comp_ref_re, line)
            if srch_result:
                ref = srch_result.group(1)
                parts[ref] = None
                continue  # Reference found, so continue with next line.

            # Search for symbol library associated with the part reference.
            srch_result = re.search(comp_lib_re, line)
            if srch_result:
                part = Part()
                part.lib = srch_result.group(1).lower()
                part.part = srch_result.group(2)
                parts[ref] = part
                continue  # Library found, so continue with next line.

    # For each symbol, store the path to the file associated with that symbol's library.
    for part in parts.values():
        if part:
            part.lib_file = sym_lib_files.get(part.lib, None)

    return parts


def fillin_part_info_from_lib(ref, parts):
    '''Fill-in part information from its associated library file.'''

    try:
        part = parts[ref]
    except Exception:
        debug_dialog(ref + 'was not found in the netlist!')
        raise Exception(ref + 'was not found in the netlist!')

    part.pins = {}  # Store part's pin information here.
    part.units = set()  # Store list of part's units here.

    # Find the part in the library and get the info for each pin.
    with open(part.lib_file, 'r') as fp:
        part_found = False
        for line in fp:
            if part_found:
                if line.startswith('ENDDEF'):
                    # Found the end of the desired part def, so we're done.
                    break

                if line.startswith('X '):
                    # Read pin information records once the desired part def is found.
                    pin_info = line.split()
                    pin = Pin()
                    pin.num = pin_info[2]
                    pin.name = pin_info[1]
                    pin.func = pin_info[11]
                    pin.unit = pin_info[9]
                    part.pins[pin.num] = pin
                    part.units.add(pin.unit)

                continue

            # Look for the start of the desired part's definition.
            part_found = (re.search(r'^DEF\s+' + part.part + r'\s+', line) or
                re.search(r'^ALIAS\s+([^\s]+\s+)*' + part.part + r'\s+', line))


def guess_netlist_file():
    '''Try to find the netlist file for this PCB.'''

    design_name = os.path.splitext(os.path.abspath(
        GetBoard().GetFileName()))[0]
    netlist_file_name = design_name + '.net'
    if os.path.isfile(netlist_file_name):
        return netlist_file_name
    return ''


class PinContention:
    '''Class for checking contention between pins on the same net.'''

    def __init__(self):
        # Initialize the pin contention matrix.
        OK, WARNING, ERROR = 0, 1, 2
        pin_funcs = ['I', 'O', 'B', 'T', 'W', 'w', 'P', 'U', 'C', 'E', 'N']
        INPUT, OUTPUT, BIDIR, TRISTATE, PWRIN, PWROUT, PASSIVE, UNSPEC, OPENCOLL, OPENEMIT, NOCONNECT = pin_funcs
        erc_matrix = {f:{ff: OK for ff in pin_funcs} for f in pin_funcs}
        erc_matrix[OUTPUT][OUTPUT] = ERROR
        erc_matrix[TRISTATE][OUTPUT] = WARNING
        erc_matrix[UNSPEC][INPUT] = WARNING
        erc_matrix[UNSPEC][OUTPUT] = WARNING
        erc_matrix[UNSPEC][BIDIR] = WARNING
        erc_matrix[UNSPEC][TRISTATE] = WARNING
        erc_matrix[UNSPEC][PASSIVE] = WARNING
        erc_matrix[UNSPEC][UNSPEC] = WARNING
        erc_matrix[PWRIN][TRISTATE] = WARNING
        erc_matrix[PWRIN][UNSPEC] = WARNING
        erc_matrix[PWROUT][OUTPUT] = ERROR
        erc_matrix[PWROUT][BIDIR] = WARNING
        erc_matrix[PWROUT][TRISTATE] = ERROR
        erc_matrix[PWROUT][UNSPEC] = WARNING
        erc_matrix[PWROUT][PWROUT] = ERROR
        erc_matrix[OPENCOLL][OUTPUT] = ERROR
        erc_matrix[OPENCOLL][TRISTATE] = ERROR
        erc_matrix[OPENCOLL][UNSPEC] = WARNING
        erc_matrix[OPENCOLL][PWROUT] = ERROR
        erc_matrix[OPENEMIT][OUTPUT] = ERROR
        erc_matrix[OPENEMIT][BIDIR] = WARNING
        erc_matrix[OPENEMIT][TRISTATE] = WARNING
        erc_matrix[OPENEMIT][UNSPEC] = WARNING
        erc_matrix[OPENEMIT][PWROUT] = ERROR
        erc_matrix[NOCONNECT][INPUT] = ERROR
        erc_matrix[NOCONNECT][OUTPUT] = ERROR
        erc_matrix[NOCONNECT][BIDIR] = ERROR
        erc_matrix[NOCONNECT][TRISTATE] = ERROR
        erc_matrix[NOCONNECT][PASSIVE] = ERROR
        erc_matrix[NOCONNECT][UNSPEC] = ERROR
        erc_matrix[NOCONNECT][PWRIN] = ERROR
        erc_matrix[NOCONNECT][PWROUT] = ERROR
        erc_matrix[NOCONNECT][OPENCOLL] = ERROR
        erc_matrix[NOCONNECT][OPENEMIT] = ERROR
        erc_matrix[NOCONNECT][NOCONNECT] = ERROR

        for s in pin_funcs:
            for d in pin_funcs:
                if erc_matrix[s][d] != erc_matrix[d][s]:
                    err_level = max(erc_matrix[s][d], erc_matrix[d][s])
                    erc_matrix[s][d] = err_level
                    erc_matrix[d][s] = err_level

class NetNameDialog(wx.Dialog):
    '''Class for getting a new net name from the user.'''

    def __init__(self, *args, **kwargs):
        wx.Dialog.__init__(self, None, title="Set Net Name")

        self.net_name = kwargs.pop('net_name', '')

        panel = wx.Panel(self)

        self.name_field = LabelledTextCtrl(panel, 'Net Name:', self.net_name, 'Enter name for new net.')

        self.ok_btn = wx.Button(panel, label='OK')
        self.cancel_btn = wx.Button(panel, label='Cancel')
        self.ok_btn.Bind(wx.EVT_BUTTON, self.set_net_name, self.ok_btn)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.cancel, self.cancel_btn)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddSpacer(WIDGET_SPACING)
        btn_sizer.Add(self.ok_btn, flag=wx.ALL | wx.ALIGN_CENTER)
        btn_sizer.AddSpacer(WIDGET_SPACING)
        btn_sizer.Add(self.cancel_btn, flag=wx.ALL | wx.ALIGN_CENTER)
        btn_sizer.AddSpacer(WIDGET_SPACING)

        # Create a vertical sizer to hold everything in the panel.
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.name_field, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, WIDGET_SPACING)

        # Size the panel.
        panel.SetSizer(sizer)
        panel.Layout()
        panel.Fit()

        # Finally, size the frame that holds the panel.
        self.Fit()

        # Show the dialog box.
        self.ShowModal()

    def set_net_name(self, evt):
        self.net_name = self.name_field.ctrl.GetValue()
        self.Destroy()

    def cancel(self, evt):
        self.net_name = None
        self.Destroy()
        
def wire_it_callback(evt):
    '''Create a wire between selected pads.'''

    # Get the identifiers of the nets attached to the selected pads.
    brd = GetBoard()
    cnct = brd.GetConnectivity()
    pads = [p for p in brd.GetPads() if p.IsSelected()]
    net_codes = list(set([p.GetNetCode() for p in brd.GetPads() if p.IsSelected()]))

    # Remove the no-connect net from the list of net IDs.
    no_connect = 0  # PCBNEW ID for the no-connect net.
    try:
        net_codes.remove(no_connect)
    except Exception:
        pass

    # Pads on different nets can't be wired together.
    if len(net_codes) > 1:
        debug_dialog("Can't connect pads on different nets")
        return

    # Wire the selected pads together. If one or more of the pads
    # is already connected to a net, then connect any unconnected pads
    # to the same net. Otherwise, all the pads are currently unconnected
    # so create a new net and connect all the pads to it.
    try:
        # Get the net if it exists.
        net = brd.FindNet(net_codes[0])
    except IndexError:
        # If no net exists, ask the user for the name of the new net.
        net_namer = NetNameDialog(parent=None)
        # Exit if the user cancels the operation by not entering a name.
        if not net_namer.net_name:
            return
        # Create a new net with the name given by the user.
        net = NETINFO_ITEM(brd, net_namer.net_name)
        brd.Add(net)  # Add new net to the board.

    # Connect all the selected pads to the net.
    for pad in pads:
        cnct.Add(pad)
        pad.SetNet(net)

    # Update the board to show the new connections.
    brd.BuildListOfNets()
    cnct.RecalculateRatsnest()
    Refresh()

def cut_it_callback(evt):
    '''Remove wires from selected pads.'''

    # Get the selected pads.
    brd = GetBoard()
    cnct = brd.GetConnectivity()
    pads = [p for p in brd.GetPads() if p.IsSelected()]

    # Disconnect the pads by moving them to the no-connect net.
    no_connect = 0  # PCBNEW ID for the no-connect net.
    for pad in pads:
        cnct.Remove(pad)
        pad.SetNetCode(no_connect)

    # Update the board to show the removed connections.
    brd.BuildListOfNets()
    cnct.RecalculateRatsnest()
    Refresh()

def swap_it_callback(evt):
    '''Swap wires between two selected pads.'''

    # Get the selected pads.
    brd = GetBoard()
    pads = [p for p in brd.GetPads() if p.IsSelected()]

    # Report error if trying to swap more or less than two pads.
    if len(pads) != 2:
        debug_dialog('To swap pads, you must select two pads and only two pads!')
        return

    # Swap nets assigned to the two pads.
    pad0_net = pads[0].GetNet()
    pads[0].SetNet(pads[1].GetNet())
    pads[1].SetNet(pad0_net)

    # Update the board to show the swapped connections.
    brd.BuildListOfNets()
    brd.GetConnectivity().RecalculateRatsnest()
    Refresh()

original_netlist = {}

def get_netlist():
    '''Create a dict with part ref & pad num as the key and attached net as the value.'''
    netlist = {}
    for pad in GetBoard().GetPads():
        pad_key = pad.GetParent().GetReference(), pad.GetPadName()
        netlist[pad_key] = pad.GetNetname(), pad.GetNetCode()
    return netlist

class DumpDialog(wx.Dialog):
    '''Class for getting filenames for dumping netlist changes.'''

    def __init__(self, *args, **kwargs):
        try:
            wx.Dialog.__init__(self, None, title="Dump Wiring Changes")

            self.netlist_name = kwargs.pop('netlist_name', '')
            self.dump_name = kwargs.pop('dump_name', '')

            panel = wx.Panel(self)

            # File browser widget for getting netlist file for this layout.
            # netlist_file_wildcard = 'Netlist File|*.net|All Files|*.*'
            # self.netlist_file_picker = DnDFilePickerCtrl(
            #     parent=panel,
            #     labelText='Netlist File:',
            #     buttonText='Browse',
            #     toolTip='Drag-and-drop the netlist file associated with this layout or browse for file or enter file name.',
            #     dialogTitle='Select netlist file associated with this layout',
            #     initialValue=guess_netlist_file(),
            #     fileMask=netlist_file_wildcard,
            #     fileMode=wx.FD_OPEN)
            # self.Bind(wx.EVT_FILEPICKER_CHANGED, self.netlist_file_handler, self.netlist_file_picker)

            # File browser widget for selecting the file to receive the netlist changes.
            dump_file_wildcard = 'Dump File|*.txt|All Files|*.*'
            self.dump_file_picker = DnDFilePickerCtrl(
                parent=panel,
                labelText='Netlist Changes File:',
                buttonText='Browse',
                toolTip='Drag-and-drop file or browse for file or enter file name.',
                dialogTitle='Select file to store netlist changes',
                initialValue='',
                fileMask=dump_file_wildcard,
                fileMode=wx.FD_OPEN)
            self.Bind(wx.EVT_FILEPICKER_CHANGED, self.dump_file_handler, self.dump_file_picker)

            self.dump_btn = wx.Button(panel, label='Dump')
            self.cancel_btn = wx.Button(panel, label='Cancel')
            self.dump_btn.Bind(wx.EVT_BUTTON, self.do_dump, self.dump_btn)
            self.cancel_btn.Bind(wx.EVT_BUTTON, self.cancel, self.cancel_btn)

            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            btn_sizer.AddSpacer(WIDGET_SPACING)
            btn_sizer.Add(self.dump_btn, flag=wx.ALL | wx.ALIGN_CENTER)
            btn_sizer.AddSpacer(WIDGET_SPACING)
            btn_sizer.Add(self.cancel_btn, flag=wx.ALL | wx.ALIGN_CENTER)
            btn_sizer.AddSpacer(WIDGET_SPACING)

            # Create a vertical sizer to hold everything in the panel.
            sizer = wx.BoxSizer(wx.VERTICAL)
            # sizer.Add(self.netlist_file_picker, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
            sizer.Add(self.dump_file_picker, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
            sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, WIDGET_SPACING)

            # Size the panel.
            panel.SetSizer(sizer)
            panel.Layout()
            panel.Fit()

            # Finally, size the frame that holds the panel.
            self.Fit()

            self.ShowModal()
        except Exception as e:
            debug_dialog(repr(e))

    def netlist_file_handler(self, evt):
        pass

    def dump_file_handler(self, evt):
        self.dump_name = self.dump_file_picker.GetPath()

    def do_dump(self, evt):
        try:
            current_netlist = get_netlist()
            with open(self.dump_name, r'w') as fp:
                for (ref, num), (new_net, new_code) in sorted(current_netlist.items()):
                    old_net, old_code = original_netlist[(ref, num)]
                    if (new_net, new_code) != (old_net, old_code):
                        fp.write('Part {ref}: Pad {num} moved from Net {old_net} ({old_code}) to Net {new_net} ({new_code}).\n'.format(**locals()))
        except Exception as e:
            debug_dialog(repr(e))
        self.Destroy()

    def cancel(self, evt):
        self.Destroy()

def dump_it_callback(evt):
    '''Compare pad wiring to original netlist and write changes to a file.'''
    DumpDialog()

class WireIt(ActionPlugin):
    '''Plugin class for tools to change wiring between pads'''

    buttons = False  # Buttons currently not installed in toolbar.

    def defaults(self):
        self.name = "WireIt"
        self.category = "Layout"
        self.description = "Create/cut/swap airwires between pads."

    def Run(self):

        # Add Wire-It buttons to toolbar if they aren't there already.
        if not self.buttons:

            def findPcbnewWindow():
                '''Find the window for the PCBNEW application.'''
                windows = wx.GetTopLevelWindows()
                pcbnew = [w for w in windows if 'Pcbnew' in w.GetTitle()]
                if len(pcbnew) != 1:
                    raise Exception("Cannot find pcbnew window from title matching!")
                return pcbnew[0]

            try:
                # Find the toolbar in the PCBNEW window.
                import inspect
                import os
                filename = inspect.getframeinfo(inspect.currentframe()).filename
                path = os.path.dirname(os.path.abspath(filename))
                pcbwin = findPcbnewWindow()
                top_toolbar = pcbwin.FindWindowById(ID_H_TOOLBAR)

                # Add wire-creation button to toolbar.
                wire_it_button = wx.NewId()
                wire_it_button_bm = wx.Bitmap(os.path.join(path, 'WireIt_icons', 'wire_it.png'), wx.BITMAP_TYPE_PNG)
                top_toolbar.AddTool(wire_it_button, "Wire It", wire_it_button_bm, "Connect pads with an airwire", wx.ITEM_NORMAL)
                top_toolbar.Bind(wx.EVT_TOOL, wire_it_callback, id=wire_it_button)

                # Add wire-removal button.
                cut_it_button = wx.NewId()
                cut_it_button_bm = wx.Bitmap(os.path.join(path, 'WireIt_icons', 'cut_it.png'), wx.BITMAP_TYPE_PNG)
                top_toolbar.AddTool(cut_it_button, "Cut It", cut_it_button_bm, "Disconnect airwires from pads", wx.ITEM_NORMAL)
                top_toolbar.Bind(wx.EVT_TOOL, cut_it_callback, id=cut_it_button)

                # Add pad-swap button.
                swap_it_button = wx.NewId()
                swap_it_button_bm = wx.Bitmap(os.path.join(path, 'WireIt_icons', 'swap_it.png'), wx.BITMAP_TYPE_PNG)
                top_toolbar.AddTool(swap_it_button, "Swap It", swap_it_button_bm, "Swap airwires between two pads", wx.ITEM_NORMAL)
                top_toolbar.Bind(wx.EVT_TOOL, swap_it_callback, id=swap_it_button)

                # Add button for dumping wiring changes to a file.
                dump_it_button = wx.NewId()
                dump_it_button_bm = wx.Bitmap(os.path.join(path, 'WireIt_icons', 'dump_it.png'), wx.BITMAP_TYPE_PNG)
                top_toolbar.AddTool(dump_it_button, "Dump It", dump_it_button_bm, "Dump wiring changes to a file", wx.ITEM_NORMAL)
                top_toolbar.Bind(wx.EVT_TOOL, dump_it_callback, id=dump_it_button)

                top_toolbar.Realize()

                self.buttons = True  # Buttons now installed in toolbar.

                # Also, store the current netlist to compare against later when dumping wiring changes.
                global original_netlist
                original_netlist = get_netlist()

            except Exception as e:
                debug_dialog('ERROR:' + repr(e))

WireIt().register()



