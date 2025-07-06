bl_info = {
    "name": "TimeTracker",
    "blender": (2, 80, 0),
    "category": "System",
    "author": "OpenAI & Shushanto (BraineyBites) & EzazulHaque",
    "version": (5, 2, 1),  # bumped version
    "description": "Accurately tracks Blender file usage time with previous save history (fixed).",
}

import bpy
import time
import os
import json
import ctypes
from bpy.app.handlers import persistent
from bpy.props import StringProperty, IntProperty

# --- State & Helpers ------------------------------------------------------
class TimeTrackerState:
    is_running = False
    file_start_time = 0
    last_activity_time = 0
    active_time = 0
    file_key = "None"
    display_mode = 'days' # Changed default to 'days' to match image
    last_mouse_x = 0
    last_mouse_y = 0
    log_path = os.path.join(bpy.utils.user_resource('CONFIG'), "time_tracker_log.json")
    total_open_time = 0
    total_active_time = 0
    start_time_save = time.time()
    active_time_save = 0
    show_history = False
    previous_saves = []
    # Default for history entries, will be updated from scene property later
    max_history_entries = 5 

# ordinal for dates
def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"

# load existing log file
def load_log():
    if os.path.exists(TimeTrackerState.log_path):
        with open(TimeTrackerState.log_path, 'r') as f:
            return json.load(f)
    return {}

# save current totals and history entry
def save_log():
    TimeTrackerState.file_key = bpy.data.filepath if bpy.data.filepath else "None"
    # structured history entry
    ts = time.localtime()
    entry = {
        "date": f"{ordinal(ts.tm_mday)} {time.strftime('%b', ts)} {ts.tm_year}",
        "time": time.strftime('%H:%M', ts),
        "open_time": TimeTrackerState.total_open_time,
        "active_time": TimeTrackerState.total_active_time
    }
    TimeTrackerState.previous_saves.append(entry)
    # Ensure previous_saves respects the max_history_entries limit
    TimeTrackerState.previous_saves = TimeTrackerState.previous_saves[-TimeTrackerState.max_history_entries:]
    
    if TimeTrackerState.file_key == "None":
        return
    log_data = load_log()
    file_log = log_data.get(TimeTrackerState.file_key, {})

    file_log["total_open_time"] = TimeTrackerState.total_open_time
    file_log["total_active_time"] = TimeTrackerState.total_active_time

    file_log["history"] = TimeTrackerState.previous_saves

    log_data[TimeTrackerState.file_key] = file_log
    with open(TimeTrackerState.log_path, 'w') as f:
        json.dump(log_data, f, indent=4)

# update totals when saving file
def update_log():
    now = time.time()
    session_open = now - TimeTrackerState.start_time_save
    session_active = TimeTrackerState.active_time - TimeTrackerState.active_time_save
    TimeTrackerState.total_open_time += session_open
    TimeTrackerState.total_active_time += session_active
    save_log()
    TimeTrackerState.start_time_save = now
    TimeTrackerState.active_time_save = TimeTrackerState.active_time

# formatting display
def format_time_display(seconds, mode):
    seconds = max(0, int(seconds))
    if mode == 'seconds':
        return f"{seconds} s"
    elif mode == 'minutes':
        mins, secs = divmod(seconds, 60)
        return f"{mins:02}m {secs:02}s" # Shortened to 'm' and 's'
    elif mode == 'hours':
        hours, rem_mins = divmod(seconds // 60, 60)
        return f"{int(hours):02}h {int(rem_mins):02}m" # Shortened to 'h' and 'm'
    elif mode == 'days':
        days, rem = divmod(seconds, 86400)
        hours = rem // 3600
        return f"{int(days)}d {int(hours)}h" # Shortened to 'd' and 'h'
    return f"{seconds} s"

# check active window on Windows
def is_blender_active_window():
    if os.name == 'nt':
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == os.getpid()
    return True

# timer starter
def start_time_tracker():
    if not TimeTrackerState.is_running:
        try:
            bpy.ops.wm.time_tracker_timer()
        except:
            pass
    return None

# redraw panel periodically
def refresh_time_tracker_panel():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return 1.0

# --- Operators & Panel ---------------------------------------------------
class TT_OT_TimerOperator(bpy.types.Operator):
    bl_idname = "wm.time_tracker_timer"
    bl_label = "Start Time Tracking"
    _timer = None

    def modal(self, context, event):
        now = time.time()
        if is_blender_active_window():
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                if event.mouse_x != TimeTrackerState.last_mouse_x or event.mouse_y != TimeTrackerState.last_mouse_y:
                    TimeTrackerState.active_time += now - TimeTrackerState.last_activity_time
                    TimeTrackerState.last_activity_time = now
                    TimeTrackerState.last_mouse_x = event.mouse_x
                    TimeTrackerState.last_mouse_y = event.mouse_y
            elif event.value == 'PRESS':
                TimeTrackerState.active_time += now - TimeTrackerState.last_activity_time
                TimeTrackerState.last_activity_time = now
        else:
            TimeTrackerState.last_activity_time = now
        return {'PASS_THROUGH'}

    def execute(self, context):
        if TimeTrackerState.is_running:
            return {'CANCELLED'}
        TimeTrackerState.is_running = True
        now = time.time()
        TimeTrackerState.file_start_time = now
        TimeTrackerState.last_activity_time = now
        TimeTrackerState.active_time = 0
        TimeTrackerState.last_mouse_x = 0
        TimeTrackerState.last_mouse_y = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        update_log()
        TimeTrackerState.is_running = False

class TT_OT_SetDisplayMode(bpy.types.Operator):
    bl_idname = "wm.set_display_mode"
    bl_label = "Set Display Mode"
    mode: StringProperty()

    def execute(self, context):
        TimeTrackerState.display_mode = self.mode
        return {'FINISHED'}

class TT_OT_ToggleHistory(bpy.types.Operator):
    bl_idname = "wm.toggle_history"
    bl_label = "Toggle Save History"

    def execute(self, context):
        TimeTrackerState.show_history = not TimeTrackerState.show_history
        return {'FINISHED'}

class TT_OT_ClearHistory(bpy.types.Operator):
    bl_idname = "wm.clear_history"
    bl_label = "Clear History"

    def execute(self, context):
        log_data = load_log()
        key = TimeTrackerState.file_key
        if key in log_data:
            log_data[key]["history"] = []
            log_data[key]["total_open_time"] = 0
            log_data[key]["total_active_time"] = 0
            with open(TimeTrackerState.log_path, 'w') as f:
                json.dump(log_data, f, indent=4)
        TimeTrackerState.total_open_time = 0
        TimeTrackerState.total_active_time = 0
        TimeTrackerState.previous_saves = []
        return {'FINISHED'}

# This operator is no longer directly called by the UI's `prop`
# The `update` callback of the IntProperty handles the logic.
# It's kept here for completeness if direct calls were desired.
class TT_OT_SetMaxHistoryEntries(bpy.types.Operator):
    bl_idname = "wm.set_max_history_entries"
    bl_label = "Set Max History Entries"
    count: IntProperty()

    def execute(self, context):
        TimeTrackerState.max_history_entries = max(3, min(100, self.count))
        # Re-apply the limit to existing history immediately
        TimeTrackerState.previous_saves = TimeTrackerState.previous_saves[-TimeTrackerState.max_history_entries:]
        return {'FINISHED'}

class TT_PT_MainPanel(bpy.types.Panel):
    bl_label = "Time Tracker"
    bl_idname = "TT_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TimeTracker'

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Current File: {os.path.basename(TimeTrackerState.file_key)}", icon='FILE_BLEND')
        layout.separator()

        now = time.time()
        opened = now - TimeTrackerState.file_start_time
        active = TimeTrackerState.active_time
        mode = TimeTrackerState.display_mode

        # Display mode buttons
        row = layout.row(align=True)
        for lbl in ['seconds', 'minutes', 'hours', 'days']:
            btn = row.operator("wm.set_display_mode", text=lbl.title(), depress=(mode == lbl))
            btn.mode = lbl

        layout.separator()
        col = layout.column(align=True)

        # Start Time
        col.label(text="Start Time", icon='PLAY')
        box1 = col.box()
        box1.label(text=format_time_display(opened, mode), icon='PREVIEW_RANGE')

        col.separator(factor=0.5)
        # Active Time
        col.label(text="Active Time", icon='MOUSE_LMB')
        box2 = col.box()
        box2.label(text=format_time_display(active, mode), icon='PREVIEW_RANGE')

        layout.separator()
        layout.label(text="Total Times", icon='INFO')
        tot = layout.box()
        tot.label(text=f"⏱ Total Start Time: {format_time_display(TimeTrackerState.total_open_time, mode)}")
        tot.label(text=f"💼 Total Active Time: {format_time_display(TimeTrackerState.total_active_time, mode)}")

        layout.separator()
        
        # History toggle button
        layout.operator("wm.toggle_history", icon='TRIA_DOWN' if TimeTrackerState.show_history else 'TRIA_RIGHT', text="Show Previous Saves")
        
        if TimeTrackerState.show_history:
            # New field for max history entries
            row = layout.row()
            row.label(text="Max Entries:")
            # Use context.scene.time_tracker_props.max_history_entries
            row.prop(context.scene.time_tracker_props, "max_history_entries", text="")
            
            hist = layout.box()
            # Header row: Date | Time | Start | Active
            hdr = hist.row(align=True)
            hdr.label(text="Date")
            hdr.separator(factor=0.3)
            hdr.label(text="Time")
            hdr.separator(factor=0.3)
            hdr.label(text="Start")
            hdr.separator(factor=0.3)
            hdr.label(text="Active")

            # History entries with individual boxes for gap
            for e in reversed(TimeTrackerState.previous_saves):
                entry_box = hist.box()
                r = entry_box.row(align=True)
                r.label(text=e['date'])
                r.separator(factor=0.3)
                r.label(text=e['time'])
                r.separator(factor=0.3)
                r.label(text=format_time_display(e['open_time'], mode))
                r.separator(factor=0.3)
                r.label(text=format_time_display(e['active_time'], mode))

            layout.operator("wm.clear_history", text="Clear History", icon='TRASH')

# Property Group for addon preferences
class TimeTrackerProperties(bpy.types.PropertyGroup):
    max_history_entries: IntProperty(
        name="Max History Entries",
        description="Maximum number of previous save entries to display",
        default=5, # Initial default value
        min=3,
        max=100,
        update=lambda self, context: setattr(TimeTrackerState, 'max_history_entries', self.max_history_entries)
    )

# Handler to initialize TimeTrackerState.max_history_entries after a scene is available
@persistent
def init_max_history_entries_on_load(dummy):
    if bpy.context.scene: # Ensure scene is available
        TimeTrackerState.max_history_entries = bpy.context.scene.time_tracker_props.max_history_entries

# persistent handlers
@persistent
def save_session_on_save(dummy):
    # Before updating log, ensure max_history_entries is correct if a scene is available
    if bpy.context.scene:
        TimeTrackerState.max_history_entries = bpy.context.scene.time_tracker_props.max_history_entries
    
    update_log()
    log = load_log()
    key = TimeTrackerState.file_key
    if key in log:
        TimeTrackerState.previous_saves = log[key].get("history", [])
        # Apply the current max_history_entries limit when loading history from log
        TimeTrackerState.previous_saves = TimeTrackerState.previous_saves[-TimeTrackerState.max_history_entries:]

@persistent
def on_file_load(dummy):
    now = time.time()
    TimeTrackerState.file_start_time = now
    TimeTrackerState.last_activity_time = now
    TimeTrackerState.active_time = 0
    TimeTrackerState.last_mouse_x = 0
    TimeTrackerState.last_mouse_y = 0
    TimeTrackerState.start_time_save = now
    TimeTrackerState.active_time_save = 0
    TimeTrackerState.file_key = bpy.data.filepath if bpy.data.filepath else "None"
    
    # Ensure max_history_entries is updated from the scene property *before* loading history
    if bpy.context.scene:
        TimeTrackerState.max_history_entries = bpy.context.scene.time_tracker_props.max_history_entries

    log = load_log()
    file_log = log.get(TimeTrackerState.file_key, {})
    TimeTrackerState.total_open_time = file_log.get("total_open_time", 0)
    TimeTrackerState.total_active_time = file_log.get("total_active_time", 0)
    TimeTrackerState.previous_saves = file_log.get("history", [])
    # Apply the current max_history_entries limit when loading history
    TimeTrackerState.previous_saves = TimeTrackerState.previous_saves[-TimeTrackerState.max_history_entries:]
    
    bpy.app.timers.register(start_time_tracker, first_interval=0.5)
    bpy.app.timers.register(refresh_time_tracker_panel)


# register classes
classes = [
    TT_OT_TimerOperator,
    TT_OT_SetDisplayMode,
    TT_OT_ToggleHistory,
    TT_OT_ClearHistory,
    TT_OT_SetMaxHistoryEntries,
    TT_PT_MainPanel,
    TimeTrackerProperties
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register the property group to the scene
    bpy.types.Scene.time_tracker_props = bpy.props.PointerProperty(type=TimeTrackerProperties)
    
    if save_session_on_save not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(save_session_on_save)
    if on_file_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_file_load)
    
    # Add a handler to initialize max_history_entries after a scene is loaded/available
    # This ensures bpy.context.scene is valid
    if init_max_history_entries_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(init_max_history_entries_on_load)
    if init_max_history_entries_on_load not in bpy.app.handlers.render_post: # Also run after render (for new scenes)
        bpy.app.handlers.render_post.append(init_max_history_entries_on_load)


    bpy.app.timers.register(start_time_tracker, first_interval=1.0)
    bpy.app.timers.register(refresh_time_tracker_panel)
    TimeTrackerState.start_time_save = time.time()
    TimeTrackerState.active_time_save = TimeTrackerState.active_time


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Unregister the property group safely
    if hasattr(bpy.types.Scene, 'time_tracker_props'):
        del bpy.types.Scene.time_tracker_props
    
    if save_session_on_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(save_session_on_save)
    if on_file_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_file_load)
    if init_max_history_entries_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(init_max_history_entries_on_load)
    if init_max_history_entries_on_load in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.remove(init_max_history_entries_on_load)

    if TimeTrackerState.is_running:
        try:
            # Correct way to cancel a modal operator from unregister
            wm = bpy.context.window_manager
            if hasattr(TT_OT_TimerOperator, "_timer") and TT_OT_TimerOperator._timer:
                wm.event_timer_remove(TT_OT_TimerOperator._timer)
            update_log() # Ensure logs are saved on unregister if running
        except Exception as e:
            print(f"Error during unregister timer cancellation: {e}")
            pass # Or log the error
    TimeTrackerState.is_running = False

if __name__ == "__main__":
    unregister()
    register()