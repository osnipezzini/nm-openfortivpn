/*
    SPDX-FileCopyrightText: 2017 Jan Grulich <jgrulich@redhat.com>

    SPDX-License-Identifier: LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL
*/

#ifndef PLASMA_NM_OPENFORTIVPN_WIDGET_H
#define PLASMA_NM_OPENFORTIVPN_WIDGET_H

#include <NetworkManagerQt/VpnSetting>

#include "settingwidget.h"

class OpenfortivpnWidgetPrivate;

class OpenfortivpnWidget : public SettingWidget
{
    Q_OBJECT
    Q_DECLARE_PRIVATE(OpenfortivpnWidget)
public:
    explicit OpenfortivpnWidget(const NetworkManager::VpnSetting::Ptr &setting, QWidget *parent = nullptr, Qt::WindowFlags f = {});
    ~OpenfortivpnWidget() override;

    void loadConfig(const NetworkManager::Setting::Ptr &setting) override;
    void loadSecrets(const NetworkManager::Setting::Ptr &setting) override;
    QVariantMap setting() const override;
    bool isValid() const override;

private Q_SLOTS:
    void showAdvanced();

private:
    OpenfortivpnWidgetPrivate *const d_ptr;
};

#endif // PLASMA_NM_OPENFORTIVPN_WIDGET_H
