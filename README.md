# dotfiles

linux/macos environment files

## Overview

You can cherry-pick individual files from this repository as needed. Alternatively this repository is setup in such a way
that with some git _"trickery"_ you can source _dot files_ directly from this repository. If you choose to go down this latter
route it is highly recommended that you fork this repo before using it for your local machines. For clarity this repository is
purpose built for development environments (usually ephemeral-ish) that I work within. As such, some of the configuration
defined in these _dot files_ may not meet your needs/requirements. 

The remainder of this readme is dedicated to using `git` to automate the lifecycle management of these files on a local
machine. 

### Background

The general idea for this _dot files_ management pattern came from a post from [Atlassian](https://www.atlassian.com/git/tutorials/dotfiles) 
(which came from discussions on HackerNews). The high level concept is that you use a _git repository_ (with a custom name) in your 
home directory to allow you to easily pull updated dot files from a git repo. This local repository is configured in such a way that 
it only tracks files which are **explicitly** added to it. Meaning, by default, it ignores all the files in your home directory 
(or sub directories) unless it is told to manage those files as part of your _dot files_. 
 
## Initial Setup

The following are a set of bash script commands to run in your home directory (the root of your home directory). Note that there are two lines below (for `user.name` and `user.email`) that need to be fixed prior to running the script. It's suggested the script file be named `.dotsetup.sh` as that will automatically be git-ignored.

```bash
# alias a customized git command to "dot" to make it easier to work with the repo:
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases

# Have git ignore the `.dotfiles` folder as that's where the git repo config has been placed
rm -fr .gitignore
echo ".dotfiles" >> .gitignore
echo ".dotsetup.sh" >> .gitignore

# clone and configure the repo:
rm -fr .dotfiles
rm -fr .git
git clone --bare https://github.com/jsco2t/dotfiles.git $HOME/.dotfiles

# configure user for repo
dot config --local status.showUntrackedFiles no
dot config --local user.name "user name"
dot config --local user.email "email@address"

# post-clone cleanup
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases

dot fetch
dot reset --hard
dot pull origin main
```

If you are going to be performing development (ex: creating branches for development) you may want to clone the repository as a non-bare repo. The following should accomplish this. 

```bash
# alias a customized git command to "dot" to make it easier to work with the repo:
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/'
shopt -s expand_aliases

# Have git ignore the `.dotfiles` folder as that's where the git repo config has been placed
rm -fr .gitignore
echo ".dotfiles" >> .gitignore
echo ".dotsetup.sh" >> .gitignore

# clone and configure the repo:
rm -fr .dotfiles
rm -fr .git
git init --separate-git-dir=$HOME/.dotfiles -b main
dot remote add origin https://github.com/jsco2t/dotfiles.git

dot config --local status.showUntrackedFiles no
dot config --local user.name "user name"
dot config --local user.email "email@address"

alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
shopt -s expand_aliases
dot fetch
dot reset --hard origin/main
dot branch --set-upstream-to=origin/main main
dot pull origin main
```

You will then need to add the following into your `.bashrc` (or `.zshrc`):

```bash
alias dot='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
```

If this has worked as expected - you should be able to open a **new** shell and run:

``` bash
dot pull
```

And the `pull` command should work as expected.

## Working with the `dotfiles` repo

To help formalize working with this repository the `git` command is aliased to `dot` with the necessary configuration to work with the dotfiles repo. What this means in practice is that when working with the dotfiles repo you need to use `dot` instead of `git` (`dot add`, `dot commit`, `dot push`, `dot pull`...etc).
