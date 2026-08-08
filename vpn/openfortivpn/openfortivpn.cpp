/*
    SPDX-FileCopyrightText: 2016 Jan Grulich <jgrulich@redhat.com>

    SPDX-License-Identifier: LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL
*/

#include "openfortivpn.h"
#include "openfortivpnauth.h"
#include "openfortivpnwidget.h"

#include <KPluginFactory>

K_PLUGIN_CLASS_WITH_JSON(OpenfortivpnUiPlugin, "plasmanetworkmanagement_openfortivpnui.json")

OpenfortivpnUiPlugin::OpenfortivpnUiPlugin(QObject *parent, const QVariantList &)
    : VpnUiPlugin(parent)
{
}

OpenfortivpnUiPlugin::~OpenfortivpnUiPlugin() = default;

SettingWidget *OpenfortivpnUiPlugin::widget(const NetworkManager::VpnSetting::Ptr &setting, QWidget *parent)
{
    return new OpenfortivpnWidget(setting, parent);
}

SettingWidget *OpenfortivpnUiPlugin::askUser(const NetworkManager::VpnSetting::Ptr &setting, const QStringList &hints, QWidget *parent)
{
    return new OpenfortivpnAuthDialog(setting, hints, parent);
}

QString OpenfortivpnUiPlugin::suggestedFileName(const NetworkManager::ConnectionSettings::Ptr &connection) const
{
    Q_UNUSED(connection);
    return {};
}

#include "openfortivpn.moc"

#include "moc_openfortivpn.cpp"
