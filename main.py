from textual.app import App, ComposeResult
from textual import work, on
from textual.worker import Worker, WorkerState
from textual.theme import Theme
from textual.widgets import Button, Log, DirectoryTree, Input, Collapsible
from textual.containers import Horizontal

from typing import Iterable
from pathlib import Path

import asyncio
import os
import signal


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

    def on_mount(self):
        self.register_theme(flexoki_light_theme)
        self.theme = "flexoki_light"
        self.title = "Run Processing"

    def compose(self) -> ComposeResult:
        with Horizontal(id="sketchbook-directory") as container:
            container.border_title = "Sketchbook Directory"
            yield Input("~/sketchbook/")
        with Collapsible(
            title="Select sketch", id="directory-tree-container"
        ) as container:
            container.border_title = None
            yield FilteredDirectoryTree("~/sketchbook/", id="select-sketch-dir")
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

        with Log(
            "Processing log", id="processing-log", auto_scroll=True
        ) as processing_logs:
            processing_logs.border_title = "Processing logs"

    @on(Input.Submitted, "#sketch-directory")
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
    def stop_processing_handler(self) -> None:
        if self.processing_process:
            # Processing spawns a Java process, just killing the
            # Processing process doesn't kill the Java window; killpg is "kill process group"
            os.killpg(os.getpgid(self.processing_process.pid), signal.SIGTERM)

    @on(Worker.StateChanged)
    def worker_state_change_handler(self, event: Worker.StateChanged) -> None:
        # TODO: handle WorkerState.ERROR and WorkerState.CANCELLED
        worker_name = event.worker.name
        state = event.state
        print(f"worker name: {worker_name}, state: {state}")
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
            preexec_fn=os.setsid,  # creates a process group, so processing can be stopped from the app
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
