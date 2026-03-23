from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBezierPath,
    NSColor,
    NSDragOperationCopy,
    NSDragOperationNone,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMenu,
    NSMenuItem,
    NSOpenPanel,
    NSPasteboardURLReadingFileURLsOnlyKey,
    NSPasteboardTypeFileURL,
    NSModalResponseOK,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSWorkspace,
    NSMakeRect,
    NSURL,
    NSView,
)
from Foundation import NSObject, NSString

from .models import DEFAULT_MODEL_ID, MODEL_BY_ID, MODEL_OPTIONS, JobProgress, JobRequest, JobResult, Preferences
from .preferences import DEFAULT_OUTPUT_ROOT, PreferenceStore
from .worker import JobRunner


MEDIA_EXTENSIONS = {
    "mp4",
    "mov",
    "m4v",
    "mkv",
    "avi",
    "wmv",
    "mp3",
    "wav",
    "flac",
    "aac",
    "m4a",
    "aiff",
    "ogg",
    "opus",
}


def _title_width(title: str) -> float:
    title_string = NSString.stringWithString_(title)
    attributes = {NSFontAttributeName: NSFont.menuBarFontOfSize_(0)}
    measured = title_string.sizeWithAttributes_(attributes)
    return max(38.0, measured.width + 20.0)


class DropStatusView(NSView):
    owner = objc.ivar()
    statusItem = objc.ivar()
    title = objc.ivar()
    dragActive = objc.ivar()

    def initWithFrame_owner_statusItem_(self, frame, owner, status_item):
        self = objc.super(DropStatusView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.owner = owner
        self.statusItem = status_item
        self.title = "SubbeX"
        self.dragActive = False
        self.registerForDraggedTypes_([NSPasteboardTypeFileURL])
        self.setToolTip_("Click for menu or drop a media file to transcribe locally.")
        return self

    def setTitle_(self, title):
        self.title = title
        self.setFrameSize_((_title_width(title), self.frame().size.height))
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        bounds = self.bounds()
        if self.dragActive:
            NSColor.controlAccentColor().set()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 6.0, 6.0)
            path.fill()
            text_color = NSColor.whiteColor()
        else:
            text_color = NSColor.labelColor()

        title_string = NSString.stringWithString_(self.title)
        attributes = {
            NSFontAttributeName: NSFont.menuBarFontOfSize_(0),
            NSForegroundColorAttributeName: text_color,
        }
        text_size = title_string.sizeWithAttributes_(attributes)
        origin_x = (bounds.size.width - text_size.width) / 2.0
        origin_y = (bounds.size.height - text_size.height) / 2.0 + 0.5
        title_string.drawAtPoint_withAttributes_((origin_x, origin_y), attributes)

    def mouseDown_(self, event):
        self.owner.show_menu()

    def draggingEntered_(self, sender):
        urls = self._file_urls_from_sender(sender)
        if not urls:
            return NSDragOperationNone
        self.dragActive = True
        self.setNeedsDisplay_(True)
        return NSDragOperationCopy

    def draggingExited_(self, sender):
        self.dragActive = False
        self.setNeedsDisplay_(True)

    def prepareForDragOperation_(self, sender):
        return True

    def performDragOperation_(self, sender):
        urls = self._file_urls_from_sender(sender)
        self.dragActive = False
        self.setNeedsDisplay_(True)
        if not urls:
            return False
        self.owner.handle_paths([Path(str(url.path())) for url in urls])
        return True

    def concludeDragOperation_(self, sender):
        self.dragActive = False
        self.setNeedsDisplay_(True)

    def _file_urls_from_sender(self, sender):
        pasteboard = sender.draggingPasteboard()
        options = {NSPasteboardURLReadingFileURLsOnlyKey: True}
        return pasteboard.readObjectsForClasses_options_([NSURL], options) or []


class SubbeXApp(NSObject):
    statusItem = objc.ivar()
    statusView = objc.ivar()
    menu = objc.ivar()
    store = objc.ivar()
    preferences = objc.ivar()
    runner = objc.ivar()
    lastOutputFolder = objc.ivar()
    statusMessage = objc.ivar()
    processingProgress = objc.ivar()

    def init(self):
        self = objc.super(SubbeXApp, self).init()
        if self is None:
            return None
        self.store = PreferenceStore()
        self.preferences = self.store.load()
        self.lastOutputFolder = None
        self.statusMessage = "Idle"
        self.processingProgress = None
        self.runner = JobRunner(
            on_progress=self.handle_progress,
            on_complete=self.handle_completion,
            on_error=self.handle_error,
            on_state_changed=self.handle_state_changed,
        )
        return self

    def applicationDidFinishLaunching_(self, notification):
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        initial_width = _title_width("SubbeX")
        self.statusView = DropStatusView.alloc().initWithFrame_owner_statusItem_(NSMakeRect(0, 0, initial_width, 22), self, self.statusItem)
        self.statusItem.setView_(self.statusView)
        self.menu = NSMenu.alloc().init()
        self.refresh_menu()
        self.update_status_title()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):
        return False

    def show_menu(self):
        self.refresh_menu()
        self.statusItem.popUpStatusItemMenu_(self.menu)

    def refresh_menu(self):
        self.menu.removeAllItems()

        status_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(self._status_line(), None, "")
        status_item.setEnabled_(False)
        self.menu.addItem_(status_item)

        if self.runner.is_busy():
            queue_depth = self.runner.pending_count()
            queue_note = "Processing current file now." if queue_depth == 0 else f"Queued after current file: {queue_depth}"
        else:
            queue_note = "Drop media on the menu bar item or choose files here."
        note_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(queue_note, None, "")
        note_item.setEnabled_(False)
        self.menu.addItem_(note_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        select_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Select Media Files…", "chooseFiles:", "")
        select_item.setTarget_(self)
        self.menu.addItem_(select_item)

        reveal_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Reveal Export Folder", "revealExportFolder:", "")
        reveal_item.setTarget_(self)
        reveal_item.setEnabled_(True)
        self.menu.addItem_(reveal_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        model_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(self._model_menu_title(), None, "")
        model_submenu = NSMenu.alloc().init()
        for option in MODEL_OPTIONS:
            entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"{option.menu_title}  ({option.description})",
                "selectModel:",
                "",
            )
            entry.setTarget_(self)
            entry.setRepresentedObject_(option.model_id)
            entry.setState_(1 if option.model_id == self.preferences.model_id else 0)
            model_submenu.addItem_(entry)
        self.menu.setSubmenu_forItem_(model_submenu, model_item)
        self.menu.addItem_(model_item)

        offset_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Set Timing Offset…  ({self.preferences.offset_seconds:+.2f}s)",
            "setOffset:",
            "",
        )
        offset_item.setTarget_(self)
        self.menu.addItem_(offset_item)

        move_original_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Move Original Into Export Folder",
            "toggleMoveOriginal:",
            "",
        )
        move_original_item.setTarget_(self)
        move_original_item.setState_(1 if self.preferences.move_original else 0)
        self.menu.addItem_(move_original_item)

        export_folder_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Choose Export Folder…  ({self.preferences.output_root})",
            "chooseExportFolder:",
            "",
        )
        export_folder_item.setTarget_(self)
        self.menu.addItem_(export_folder_item)

        reset_folder_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Reset Export Folder to Default",
            "resetExportFolder:",
            "",
        )
        reset_folder_item.setTarget_(self)
        self.menu.addItem_(reset_folder_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        ffmpeg_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Check ffmpeg Setup", "checkFfmpeg:", "")
        ffmpeg_item.setTarget_(self)
        self.menu.addItem_(ffmpeg_item)

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit SubbeX", "quitApp:", "")
        quit_item.setTarget_(self)
        self.menu.addItem_(quit_item)

    def _status_line(self) -> str:
        if self.processingProgress is None:
            return self.statusMessage
        return f"{self.processingProgress.detail} ({int(self.processingProgress.fraction * 100)}%)"

    def _model_menu_title(self) -> str:
        option = MODEL_BY_ID.get(self.preferences.model_id, MODEL_BY_ID[DEFAULT_MODEL_ID])
        return f"Model: {option.menu_title}"

    def update_status_title(self):
        if self.processingProgress is None:
            title = "SubbeX"
        elif self.processingProgress.phase == "preparing":
            title = "SBX Prep"
        else:
            title = f"SBX {int(self.processingProgress.fraction * 100)}%"
        self.statusView.setTitle_(title)
        self.statusItem.setLength_(_title_width(title))

    def chooseFiles_(self, sender):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(True)
        panel.setAllowedFileTypes_(sorted(MEDIA_EXTENSIONS))
        panel.setMessage_("Choose video or audio files to transcribe into SRT subtitles.")
        if panel.runModal() == NSModalResponseOK:
            urls = panel.URLs() or []
            self.handle_paths([Path(str(url.path())) for url in urls])

    def revealExportFolder_(self, sender):
        target = self.lastOutputFolder or self.preferences.output_root
        if target:
            self.reveal_in_finder(Path(target))

    def selectModel_(self, sender):
        model_id = str(sender.representedObject())
        self.preferences = self.store.update_model(self.preferences, model_id)
        self.refresh_menu()

    def toggleMoveOriginal_(self, sender):
        move_original = not self.preferences.move_original
        self.preferences = self.store.update_move_original(self.preferences, move_original)
        self.refresh_menu()

    def chooseExportFolder_(self, sender):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setCanCreateDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setDirectoryURL_(NSURL.fileURLWithPath_(str(self.preferences.output_root)))
        panel.setMessage_("Choose the dedicated folder where new subtitle exports should be saved.")
        if panel.runModal() == NSModalResponseOK:
            url = panel.URL()
            if url is not None:
                self.preferences = self.store.update_output_root(self.preferences, Path(str(url.path())))
                self.refresh_menu()

    def resetExportFolder_(self, sender):
        self.preferences = self.store.update_output_root(self.preferences, DEFAULT_OUTPUT_ROOT)
        self.refresh_menu()

    def setOffset_(self, sender):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Subtitle timing offset")
        alert.setInformativeText_("Enter a positive or negative offset in seconds. Example: -0.35")
        field_class = objc.lookUpClass("NSTextField")
        field = field_class.alloc().initWithFrame_(NSMakeRect(0, 0, 220, 24))
        field.setStringValue_(f"{self.preferences.offset_seconds:.2f}")
        alert.setAccessoryView_(field)
        alert.addButtonWithTitle_("Save")
        alert.addButtonWithTitle_("Cancel")
        response = alert.runModal()
        if response != NSAlertFirstButtonReturn:
            return

        try:
            offset_seconds = float(str(field.stringValue()).strip())
        except ValueError:
            self.show_error("Offset must be a number, such as 0.5 or -1.2.")
            return

        self.preferences = self.store.update_offset(self.preferences, offset_seconds)
        self.refresh_menu()

    def checkFfmpeg_(self, sender):
        from .ffmpeg import find_ffmpeg_tools

        try:
            tools = find_ffmpeg_tools()
        except Exception as exc:
            self.show_error(str(exc))
            return

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_("ffmpeg detected")
        alert.setInformativeText_(f"ffmpeg: {tools.ffmpeg}\nffprobe: {tools.ffprobe}")
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def quitApp_(self, sender):
        NSApplication.sharedApplication().terminate_(None)

    def handle_paths(self, paths: list[Path]):
        media_paths = [path for path in paths if path.is_file() and path.suffix.lower().lstrip(".") in MEDIA_EXTENSIONS]
        if not media_paths:
            self.show_error("Choose or drop a supported video or audio file.")
            return

        requests = [JobRequest(input_path=path, preferences=replace(self.preferences)) for path in media_paths]
        self.runner.enqueue(requests)
        queued = len(media_paths)
        self.statusMessage = f"Queued {queued} file{'s' if queued != 1 else ''}"
        self.refresh_menu()
        self.update_status_title()

    def handle_progress(self, progress: JobProgress):
        self.processingProgress = progress
        self.statusMessage = f"{progress.input_path.name}: {progress.detail}"
        self.refresh_menu()
        self.update_status_title()

    def handle_completion(self, result: JobResult):
        self.processingProgress = None
        self.lastOutputFolder = result.output_folder
        self.statusMessage = f"Finished {result.input_path.name}"
        self.refresh_menu()
        self.update_status_title()
        self.reveal_in_finder(result.output_folder)

    def handle_error(self, request: JobRequest, error: Exception):
        self.processingProgress = None
        self.statusMessage = f"Failed {request.input_path.name}"
        self.refresh_menu()
        self.update_status_title()
        self.show_error(f"{request.input_path.name}\n\n{error}")

    def handle_state_changed(self, busy: bool, queue_depth: int):
        if not busy and self.processingProgress is None:
            self.update_status_title()
        self.refresh_menu()

    def reveal_in_finder(self, path: Path):
        NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([NSURL.fileURLWithPath_(str(path))])

    def show_error(self, message: str):
        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_("SubbeX")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.runModal()
