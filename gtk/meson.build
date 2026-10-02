project('nm-openfortivpn-editor', 'c', version: '0.1.0', license: 'GPL-2.0-or-later')

gnome = import('gnome')
add_project_arguments('-Wno-deprecated-declarations', language: 'c') # GtkFileChooserNative is deprecated in GTK4 but still the portable choice
libdir = get_option('prefix') / get_option('libdir') / 'NetworkManager'
inc = include_directories('../vpn/openfortivpn') # nm-openfortivpn-service.h lives with the Plasma widget

libnm = dependency('libnm')
gmodule = dependency('gmodule-2.0')
dl = meson.get_compiler('c').find_library('dl', required: false)
res = gnome.compile_resources('editor-res', 'editor.gresource.xml')

shared_module('libnm-vpn-plugin-openfortivpn',
  'plugin.c', 'nm-vpn-plugin-utils.c',
  name_prefix: '', include_directories: inc,
  dependencies: [libnm, gmodule, dl], install: true, install_dir: libdir)

gtk3 = dependency('gtk+-3.0', required: get_option('with_gtk3'))
nma3 = dependency('libnma', required: get_option('with_gtk3'))
if gtk3.found() and nma3.found()
  shared_module('libnm-vpn-plugin-openfortivpn-editor',
    'editor.c', res,
    name_prefix: '', include_directories: inc,
    dependencies: [libnm, gmodule, gtk3, nma3], install: true, install_dir: libdir)
endif

gtk4 = dependency('gtk4', required: get_option('with_gtk4'))
nma4 = dependency('libnma-gtk4', required: get_option('with_gtk4'))
if gtk4.found() and nma4.found()
  shared_module('libnm-gtk4-vpn-plugin-openfortivpn-editor',
    'editor.c', res,
    name_prefix: '', include_directories: inc,
    dependencies: [libnm, gmodule, gtk4, nma4], install: true, install_dir: libdir)
endif
