from textual.app import App, ComposeResult
from textual import work, on
from textual.theme import Theme
from textual.widgets import Button, Log, DirectoryTree, Input

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
    def __init__(self):
        super().__init__()
        self.selected_sketch_dir = None
        self.processing_process = None

    def on_mount(self):
        self.register_theme(flexoki_light_theme)
        self.theme = "flexoki_light"
        self.title = "Run Processing"

    def compose(self) -> ComposeResult:
        yield Input("Sketch directory", id="sketch-directory")
        yield FilteredDirectoryTree(
            "/home/scossar/projects/processing/", id="select-sketch-dir"
        )
        yield Button("Launch Processing", id="launch-processing", disabled=True)
        yield Button("Stop Processing", id="stop-processing", disabled=True)
        yield Log("Processing log", id="processing-log")

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
        processing_button.label = f"Launch {self.selected_sketch_dir.stem}"

    @on(Button.Pressed, "#launch-processing")
    def launch_processing_handler(self) -> None:
        if self.selected_sketch_dir:
            self.launch_processing(self.selected_sketch_dir)
            self.query_one("#stop-processing", Button).disabled = False

    @on(Button.Pressed, "#stop-processing")
    async def stop_processing_handler(self) -> None:
        if self.processing_process:
            # this was surprisingly difficult. Processing spawns a Java process, just killing the
            # Processing process doesn't kill the Java window
            os.killpg(os.getpgid(self.processing_process.pid), signal.SIGTERM)

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
        # self.processing_process = None


if __name__ == "__main__":
    app = ProcessingApp()
    app.run()
