/*
    SPDX-FileCopyrightText: 2017 Jan Grulich <jgrulich@redhat.com>

    SPDX-License-Identifier: LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL
*/

#ifndef PLASMA_NM_OPENFORTIVPN_H
#define PLASMA_NM_OPENFORTIVPN_H

#include "vpnuiplugin.h"

#include <QVariant>

class Q_DECL_EXPORT OpenfortivpnUiPlugin : public VpnUiPlugin
{
    Q_OBJECT
public:
    explicit OpenfortivpnUiPlugin(QObject *parent = nullptr, const QVariantList & = QVariantList());
    ~OpenfortivpnUiPlugin() override;
    SettingWidget *widget(const NetworkManager::VpnSetting::Ptr &setting, QWidget *parent) override;
    SettingWidget *askUser(const NetworkManager::VpnSetting::Ptr &setting, const QStringList &hints, QWidget *parent) override;

    QString suggestedFileName(const NetworkManager::ConnectionSettings::Ptr &connection) const override;
};

#endif //  PLASMA_NM_OPENFORTIVPN_H
