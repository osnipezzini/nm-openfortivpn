add_definitions(-DTRANSLATION_DOMAIN=\"plasmanetworkmanagement_openfortivpnui\")


add_library(plasmanetworkmanagement_openfortivpnui MODULE)
target_sources(plasmanetworkmanagement_openfortivpnui PRIVATE
    openfortivpn.cpp
    openfortivpnwidget.cpp
    openfortivpnauth.cpp
    openfortivpn.h
    openfortivpnwidget.h
    openfortivpnauth.h
)
ki18n_wrap_ui(plasmanetworkmanagement_openfortivpnui openfortivpn.ui openfortivpnadvanced.ui openfortivpnauth.ui)

target_link_libraries(plasmanetworkmanagement_openfortivpnui
    plasmanm_internal
    plasmanm_editor
    KF6::CoreAddons
    KF6::I18n
    KF6::KIOWidgets
    KF6::WidgetsAddons
)

install(TARGETS plasmanetworkmanagement_openfortivpnui DESTINATION ${KDE_INSTALL_PLUGINDIR}/plasma/network/vpn)