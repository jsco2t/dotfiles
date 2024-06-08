""" common settings -------------------------
let mapleader=" "
set showmode
set so=5
set scrolloff=5
set incsearch
set number
set mouse=a
":autocmd InsertEnter * set cursorline
":autocmd InsertLeave * set nocursorline

""" plugins  --------------------------------

call plug#begin()

" Highlight copied text
Plug 'machakann/vim-highlightedyank'
" Commentary plugin
Plug 'tpope/vim-commentary'
" Surround plugin
Plug 'tpope/vim-surround'
" Vim indent plugin
Plug 'michaeljsmith/vim-indent-object'
" whichkey port for vim
Plug 'liuchengxu/vim-which-key'

call plug#end()

" Matchit plugin
:packadd! matchit


""" key mappings  ---------------------

map <leader>r <Action>(ReformatCode)
map <leader>d <Action>(Debug)
map <leader>R <Action>(RenameElement)
map <leader>c <Action>(Stop)
map <leader>z <Action>(ToggleDistractionFreeMode)
map <leader>s <Action>(SelectInProjectView)
map <leader>a <Action>(Annotate)
map <leader>h <Action>(Vcs.ShowTabbedFileHistory)
map <S-Space> <Action>(GotoNextError)
map <leader>B <Action>(ToggleLineBreakpoint)
map <leader>o <Action>(FileStructurePopup)
map <leader>b <Action>(Switcher)
map gh <Action>(ShowErrorDescription)

""" which-key customizations  ---------------------

nnoremap <silent> <leader>      :<c-u>WhichKey '<Space>'<CR>
nnoremap <silent> <localleader> :<c-u>WhichKey  ','<CR>

""" create dirs if missing when writing file  ---------------------
augroup vimrc-auto-mkdir
  autocmd!
  autocmd BufWritePre * call s:auto_mkdir(expand('<afile>:p:h'), v:cmdbang)
  function! s:auto_mkdir(dir, force)
    if !isdirectory(a:dir)
          \   && (a:force
          \       || input("'" . a:dir . "' does not exist. Create? [y/N]") =~? '^y\%[es]$')
      call mkdir(iconv(a:dir, &encoding, &termencoding), 'p')
    endif
  endfunction
augroup END

""" Change cursor shape based on mode  ---------------------

let &t_SI = "\e[6 q"
let &t_EI = "\e[2 q"

" reset the cursor on start (for older versions of vim, usually not required)
augroup myCmds
  au!
  autocmd VimEnter * silent !echo -ne "\e[2 q"
augroup END
