from textual.app import App, ComposeResult
from textual import work, on
from textual.worker import Worker, WorkerState
from textual.theme import Theme
from textual.widgets import Button, Log, DirectoryTree, Input, Collapsible
from textual.containers import Horizontal
from textual.message import Message

from typing import Iterable
from pathlib import Path

import asyncio
import os
import signal

from pyliblo3 import ServerThread, Address, make_method, send

processing = Address("localhost", 12000)


class OscServer(ServerThread):
    def __init__(self, port, app):
        ServerThread.__init__(self, port)
        self.app = app

    @make_method("/osc/config", "sss")
    def osc_config_callback(self, path, args):
        oscpath, types, name = args
        self.app.call_from_thread(
            # f"\u2190 Received response from '{path}': {args}"
            self.app.post_message,
            OscMessageReceived(path, args),
        )

    @make_method(None, None)
    def fallback(self, path, args):
        self.app.call_from_thread(self.app.post_message, OscMessageReceived(path, args))


class OscMessageReceived(Message):
    def __init__(self, path: str, args: tuple):
        super().__init__()
        self.path = path
        self.args = args


flexoki_light_theme = Theme(
    name="flexoki_light",
    primary="#100F0F",
    secondary="#D14D41",
    foreground="#100F0F",
    background="#FFFCF0",
    surface="#FFFCF0",
    success="#879A39",
    accent="#4385BE",
    warning="#D14D41",
)


class FilteredDirectoryTree(DirectoryTree):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        processing_dirs = []
        for path in paths:
            if path.is_dir():
                for entry in path.iterdir():
                    if entry.is_file() and entry.suffix == ".pde":
                        processing_dirs.append(path)
                        break
        return processing_dirs


class ProcessingApp(App):
    CSS_PATH = "styles.tcss"

    def __init__(self):
        super().__init__()
        self.selected_sketch_dir = None
        self.processing_process = None
        self.osc_server = None

    def on_mount(self):
        self.register_theme(flexoki_light_theme)
        self.theme = "flexoki_light"
        self.title = "Run Processing"

        #
        # def write_to_log(message):
        #     self.call_from_thread(osc_log.write_line, message)

        self.osc_server = OscServer(9000, app)
        self.osc_server.start()
        osc_log = self.query_one("#osc-log", Log)
        osc_log.write_line("OSC Server listening on port 9000")

    def compose(self) -> ComposeResult:
        with Horizontal(id="sketchbook-directory-container") as container:
            container.border_title = "Sketchbook Directory"
            yield Input("~/projects/processing", id="sketchbook-directory")
        with Collapsible(
            title="Select sketch", id="directory-tree-container"
        ) as container:
            container.border_title = None
            yield FilteredDirectoryTree("~/projects/processing", id="select-sketch-dir")
        with Horizontal():
            yield Button(
                "Run",
                id="launch-processing",
                variant="success",
                disabled=True,
            )
            yield Button(
                "Stop",
                id="stop-processing",
                variant="warning",
                disabled=True,
            )

        yield Horizontal(id="osc-widgets")

        with Log(
            "Processing log", id="processing-log", auto_scroll=True
        ) as processing_logs:
            processing_logs.border_title = "Processing logs"
        with Log("OSC log", id="osc-log", auto_scroll=True) as osc_log:
            osc_log.border_title = "OSC logs"

    @on(OscMessageReceived)
    async def handle_osc_message(self, event: OscMessageReceived) -> None:
        osc_log = self.query_one("#osc-log", Log)
        osc_log.write_line(f"\u2190 Received from '{event.path}': {event.args}")

        if event.path == "/osc/config":
            message_path, types, name = event.args
            new_widget = Input(id=f"osc-{name}")
            new_widget.styles.border = ("solid", "black")
            new_widget.border_title = name
            container = self.query_one("#osc-widgets")
            await container.mount(new_widget)

    @on(Input.Submitted, "#sketchbook-directory")
    def sketch_directory_handler(self, event: Input.Submitted):
        sketch_directory = event.input.value
        directory_tree_widget = self.query_one("#select-sketch-dir")
        directory_tree_widget.path = sketch_directory

    @on(FilteredDirectoryTree.DirectorySelected, "#select-sketch-dir")
    def set_sketch_dir_handler(
        self, event: FilteredDirectoryTree.DirectorySelected
    ) -> None:
        self.selected_sketch_dir = event.path
        processing_button = self.query_one("#launch-processing")
        processing_button.disabled = False
        container_title = f"Selected sketch: {self.selected_sketch_dir.stem}"
        self.query_one("#directory-tree-container").border_title = container_title

    @on(Button.Pressed, "#launch-processing")
    def launch_processing_handler(self) -> None:
        if self.selected_sketch_dir:
            self.launch_processing(self.selected_sketch_dir)
            self.query_one("#stop-processing", Button).disabled = False

    @on(Button.Pressed, "#stop-processing")
    async def stop_processing_handler(self) -> None:
        if self.processing_process:
            proc = self.processing_process
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except ProcessLookupError:
                pass  # the process is probably already terminated
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    await proc.wait()
                except ProcessLookupError:
                    pass
            finally:
                output_widget = self.query_one("#processing-log", Log)
                output_widget.write_line("Finished.")

    @on(Worker.StateChanged)
    def worker_state_change_handler(self, event: Worker.StateChanged) -> None:
        # TODO: handle WorkerState.ERROR and WorkerState.CANCELLED
        worker_name = event.worker.name
        state = event.state
        if worker_name == "launch_processing":
            if state == WorkerState.RUNNING:
                self.query_one("#launch-processing", Button).disabled = True
                self.query_one(FilteredDirectoryTree).disabled = True
            if state == WorkerState.SUCCESS:
                self.query_one("#launch-processing", Button).disabled = False
                self.query_one("#stop-processing").disabled = True
                self.query_one(FilteredDirectoryTree).disabled = False

    @work(exclusive=True)
    async def launch_processing(self, sketch: str) -> None:
        output_widget = self.query_one("#processing-log", Log)

        self.processing_process = await asyncio.create_subprocess_exec(
            "processing-java",
            f"--sketch={sketch}",
            "--run",
            stdout=asyncio.subprocess.PIPE,
            start_new_session=True,  # calls (the system call) setsid()
        )

        while True:
            line = await self.processing_process.stdout.readline()
            if not line:
                break
            output_widget.write_line(line.decode().strip())

        await self.processing_process.wait()
        self.processing_process = None


if __name__ == "__main__":
    app = ProcessingApp()
    app.run()
