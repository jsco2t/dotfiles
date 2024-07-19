#!/usr/bin/env python3

# A few notes about this utility:
#
#   1. I am not a python expert: any of the following should not be taken as example code.
#   2. This is clearly over-kill.
#   3. So why did I do it?
#       a. It seemed fun
#       b. I like TUI's
#       c. I needed an excuse to play with python more
#
# This code may or may not work, or it may work in ways you didn't intend.
#
# All of that to say - you have been warned :)
#
# Install instructions:
#
#   - On an rpi the python packages in APT are not new enough. One solution is to force a global install using pip:
#
#       pip install textual --break-system-packages
#       pip install gitpython --break-system-packages
#
#     This is likely a less than ideal solution due to the chance to break the system packages.
#

from textual import log, on
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Label, ListItem, ListView, Static, Input
from textual.validation import Length
from git import Repo

class GitRepoManager:
    r = Repo("~/.dotfiles") # use a class/static type to avoid repo object being recreated

    @property
    def repo(self):
        return self.r


# Get changes from git
def getGitChanges(repo):
    repo.remote().pull()
    diffsFromWorkingCopy = repo.index.diff(None)
    diffsFromTree = repo.index.diff("HEAD")
    diffs = diffsFromWorkingCopy + diffsFromTree
    return diffs

def printGitChanges(repo):
    diffs = getGitChanges(repo)
    for d in diffs:
        print(d.a_path)

# Handle committing and pushing code to git
def commitAllChanges(repo, message):
    changes = getGitChanges(repo)

    for change in changes:
        repo.index.add(change.a_path)

    repo.index.commit(message)

def pushChanges(repo):
    repo.remote().push().raise_if_error()

class SourceChangesList(Static):
    """List view for source changes"""

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }
    /*ListView {
        width: 100;
        height: auto;
        margin: 5 5;
    }*/
    Label {
        padding: 0 1;
    }
    #content {
        layout: grid;
        grid-size: 2 4; /* cols rows */
        height: 50%
    }
    #title {
        column-span: 2;
        height: 5;
        margin-top: 1;
        margin-left: 1;
    }
    #changes {
        column-span: 2;
        height: auto;
        width: 100;
        margin-left: 3;
        margin-top: 0;
    }
    #commitMessage {
        width: 100;
        column-span: 2;
        margin-left: 2;
        margin-top: 0;
    }
    """

    def compose(self) -> ComposeResult:
        """List of changes to commit"""

        #repo = Repo("~/.dotfiles")
        repo = GitRepoManager().repo
        changes = getGitChanges(repo)
        self.log(len(changes))

        with Container(id="content"):

            with Container(id="title"):
                yield Label("Current Changes:")

            with Container(id="changes"):
                yield ListView(
                    *[ ListItem( Label( change.a_path ) ) for change in changes ],
                    ListItem(Label("")),
                )

            with Container(id="commitMessage"):
                yield Input(
                    placeholder="Commit message",
                    validators=[
                        Length(minimum = 1),
                    ],
                    id="message",
                )

class DotUpdateApp(App):
    """Dotfiles synchronization utility."""

    BINDINGS = [
      ("d", "toggle_dark", "Toggle dark mode"),
      ("q", "quit_app", "Quit the app"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        self.log("composing")
        yield Header()
        yield SourceChangesList()
        yield Footer()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_quit_app(self) -> None:
        """An action to exit the app."""
        self.exit()

    @on(Input.Submitted, "#message")
    def on_input_changed(self, message: Input.Submitted) -> None:
        """commit updated"""
        repo = GitRepoManager().repo
        if message.value:
            commitAllChanges(repo, message.value)
            pushChanges(repo)
            self.log("Committing: " + message.value)
        else:
            self.panic("Request to commit changes was made - but no commit message was supplied")


if __name__ == "__main__":
    repo = GitRepoManager().repo

    if not repo.is_dirty():
        print("No changes, exiting...")
        exit()

    app = DotUpdateApp()
    app.run()
