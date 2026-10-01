/*
    SPDX-FileCopyrightText: 2017 Jan Grulich <jgrulich@redhat.com>

    SPDX-License-Identifier: LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL
*/

#include "openfortivpnwidget.h"
#include "ui_openfortivpn.h"
#include "ui_openfortivpnadvanced.h"

#include "nm-openfortivpn-service.h"

#include <NetworkManagerQt/Setting>

#include <KUrlRequester>

#include <QCheckBox>
#include <QDialog>
#include <QDialogButtonBox>

namespace
{
struct BoolOpt {
    const char *key;
    QCheckBox *Ui::OpenfortivpnAdvancedWidget::*box;
    bool def;
};
struct TextOpt {
    const char *key;
    QLineEdit *Ui::OpenfortivpnAdvancedWidget::*edit;
};
struct UrlOpt {
    const char *key;
    KUrlRequester *Ui::OpenfortivpnAdvancedWidget::*edit;
};

const BoolOpt boolOpts[] = {
    {NM_OPENFORTIVPN_KEY_NO_FTM_PUSH, &Ui::OpenfortivpnAdvancedWidget::noFtmPush, false},
    {NM_OPENFORTIVPN_KEY_INSECURE_SSL, &Ui::OpenfortivpnAdvancedWidget::insecureSsl, false},
    {NM_OPENFORTIVPN_KEY_SECLEVEL_1, &Ui::OpenfortivpnAdvancedWidget::seclevel1, false},
    {NM_OPENFORTIVPN_KEY_SET_ROUTES, &Ui::OpenfortivpnAdvancedWidget::setRoutes, true},
    {NM_OPENFORTIVPN_KEY_HALF_INTERNET_ROUTES, &Ui::OpenfortivpnAdvancedWidget::halfInternetRoutes, false},
    {NM_OPENFORTIVPN_KEY_SET_DNS, &Ui::OpenfortivpnAdvancedWidget::setDns, true},
    {NM_OPENFORTIVPN_KEY_USE_RESOLVCONF, &Ui::OpenfortivpnAdvancedWidget::useResolvconf, true},
    {NM_OPENFORTIVPN_KEY_PPPD_USE_PEERDNS, &Ui::OpenfortivpnAdvancedWidget::pppdUsePeerdns, false},
    {NM_OPENFORTIVPN_KEY_PPPD_ACCEPT_REMOTE, &Ui::OpenfortivpnAdvancedWidget::pppdAcceptRemote, true},
};
const TextOpt textOpts[] = {
    {NM_OPENFORTIVPN_KEY_OTP_PROMPT, &Ui::OpenfortivpnAdvancedWidget::otpPrompt},
    {NM_OPENFORTIVPN_KEY_SNI, &Ui::OpenfortivpnAdvancedWidget::sni},
    {NM_OPENFORTIVPN_KEY_CIPHER_LIST, &Ui::OpenfortivpnAdvancedWidget::cipherList},
    {NM_OPENFORTIVPN_KEY_PPPD_IPPARAM, &Ui::OpenfortivpnAdvancedWidget::pppdIpparam},
    {NM_OPENFORTIVPN_KEY_PPPD_IFNAME, &Ui::OpenfortivpnAdvancedWidget::pppdIfname},
    {NM_OPENFORTIVPN_KEY_PPPD_CALL, &Ui::OpenfortivpnAdvancedWidget::pppdCall},
    {NM_OPENFORTIVPN_KEY_IFNAME, &Ui::OpenfortivpnAdvancedWidget::ifname},
};
const UrlOpt urlOpts[] = {
    {NM_OPENFORTIVPN_KEY_PPPD_LOG, &Ui::OpenfortivpnAdvancedWidget::pppdLog},
    {NM_OPENFORTIVPN_KEY_PPPD_PLUGIN, &Ui::OpenfortivpnAdvancedWidget::pppdPlugin},
};

PasswordField::PasswordOption optionFromFlags(int flags)
{
    if (flags == NetworkManager::Setting::None) {
        return PasswordField::StoreForAllUsers;
    } else if (flags == NetworkManager::Setting::AgentOwned) {
        return PasswordField::StoreForUser;
    } else if (flags == NetworkManager::Setting::NotSaved) {
        return PasswordField::AlwaysAsk;
    }
    return PasswordField::NotRequired;
}

int flagsFromOption(PasswordField::PasswordOption o)
{
    switch (o) {
    case PasswordField::StoreForAllUsers:
        return NetworkManager::Setting::None;
    case PasswordField::StoreForUser:
        return NetworkManager::Setting::AgentOwned;
    case PasswordField::AlwaysAsk:
        return NetworkManager::Setting::NotSaved;
    default:
        return NetworkManager::Setting::NotRequired;
    }
}
}

class OpenfortivpnWidgetPrivate
{
public:
    Ui::OpenfortivpnWidget ui;
    Ui::OpenfortivpnAdvancedWidget advUi;
    NetworkManager::VpnSetting::Ptr setting;
    QDialog *advancedDlg = nullptr;
    QWidget *advancedWid = nullptr;
};

OpenfortivpnWidget::OpenfortivpnWidget(const NetworkManager::VpnSetting::Ptr &setting, QWidget *parent, Qt::WindowFlags f)
    : SettingWidget(setting, parent, f)
    , d_ptr(new OpenfortivpnWidgetPrivate)
{
    Q_D(OpenfortivpnWidget);

    d->setting = setting;

    d->ui.setupUi(this);

    d->ui.password->setPasswordOptionsEnabled(true);
    d->ui.password->setPasswordNotRequiredEnabled(true);

    // Connect for setting check
    watchChangedSetting();

    // Connect for validity check
    connect(d->ui.gateway, &QLineEdit::textChanged, this, &OpenfortivpnWidget::slotWidgetChanged);

    // Advanced configuration
    connect(d->ui.advancedButton, &QPushButton::clicked, this, &OpenfortivpnWidget::showAdvanced);

    d->advancedDlg = new QDialog(this);
    d->advancedWid = new QWidget(this);
    d->advUi.setupUi(d->advancedWid);
    d->advUi.pemPassphrase->setPasswordOptionsEnabled(true);
    d->advUi.pemPassphrase->setPasswordNotRequiredEnabled(true);
    auto layout = new QVBoxLayout(d->advancedDlg);
    layout->addWidget(d->advancedWid);
    d->advancedDlg->setLayout(layout);
    auto buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, d->advancedDlg);
    connect(buttons, &QDialogButtonBox::accepted, d->advancedDlg, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, d->advancedDlg, &QDialog::reject);
    layout->addWidget(buttons);
    KAcceleratorManager::manage(this);

    // Remove these from setting check:
    // Just popping up the advancedDlg changes nothing
    disconnect(d->ui.advancedButton, &QPushButton::clicked, this, &SettingWidget::settingChanged);
    // But the accept button does
    connect(buttons, &QDialogButtonBox::accepted, this, &SettingWidget::settingChanged);

    if (setting && !setting->isNull()) {
        loadConfig(setting);
    }
}

OpenfortivpnWidget::~OpenfortivpnWidget()
{
    delete d_ptr;
}

void OpenfortivpnWidget::loadConfig(const NetworkManager::Setting::Ptr &setting)
{
    Q_D(OpenfortivpnWidget);

    const NMStringMap data = d->setting->data();

    const QString gateway = data.value(NM_OPENFORTIVPN_KEY_GATEWAY);
    if (!gateway.isEmpty()) {
        d->ui.gateway->setText(gateway);
    }

    const QString username = data.value(NM_OPENFORTIVPN_KEY_USER);
    if (!username.isEmpty()) {
        d->ui.username->setText(username);
    }

    const NetworkManager::Setting::SecretFlags passwordFlag =
        static_cast<NetworkManager::Setting::SecretFlags>(data.value(NM_OPENFORTIVPN_KEY_PASSWORD "-flags").toInt());
    if (passwordFlag == NetworkManager::Setting::None) {
        d->ui.password->setPasswordOption(PasswordField::StoreForAllUsers);
    } else if (passwordFlag == NetworkManager::Setting::AgentOwned) {
        d->ui.password->setPasswordOption(PasswordField::StoreForUser);
    } else if (passwordFlag == NetworkManager::Setting::NotSaved) {
        d->ui.password->setPasswordOption(PasswordField::AlwaysAsk);
    } else {
        d->ui.password->setPasswordOption(PasswordField::NotRequired);
    }

    const QString caCert = data.value(NM_OPENFORTIVPN_KEY_CA);
    if (!caCert.isEmpty()) {
        d->ui.caCert->setText(caCert);
    }

    const QString userCert = data.value(NM_OPENFORTIVPN_KEY_CERT);
    if (!userCert.isEmpty()) {
        d->ui.userCert->setText(userCert);
    }

    const QString userKey = data.value(NM_OPENFORTIVPN_KEY_KEY);
    if (!userKey.isEmpty()) {
        d->ui.userKey->setText(userKey);
    }

    // From advanced dialog
    const QString trustedCert = data.value(NM_OPENFORTIVPN_KEY_TRUSTED_CERT);
    if (!trustedCert.isEmpty()) {
        d->advUi.trustedCert->setText(trustedCert);
    }

    if (!data.value(NM_OPENFORTIVPN_KEY_OTP "-flags").isEmpty()) {
        const NetworkManager::Setting::SecretFlags otpFlag =
            static_cast<NetworkManager::Setting::SecretFlags>(data.value(NM_OPENFORTIVPN_KEY_OTP "-flags").toInt());
        if (otpFlag & NetworkManager::Setting::NotSaved) {
            d->advUi.otp->setChecked(true);
        }
    }

    if (!data.value(NM_OPENFORTIVPN_KEY_2FA "-flags").isEmpty()) {
        const NetworkManager::Setting::SecretFlags tfaFlag =
            static_cast<NetworkManager::Setting::SecretFlags>(data.value(NM_OPENFORTIVPN_KEY_2FA "-flags").toInt());
        if (tfaFlag & NetworkManager::Setting::AgentOwned) {
            d->advUi.tfa->setChecked(true);
        }
    }

    // SAML login
    const QString samlLogin = data.value(NM_OPENFORTIVPN_KEY_SAML_LOGIN);
    d->advUi.saml->setChecked(samlLogin == QLatin1String("true"));

    const QString realm = data.value(NM_OPENFORTIVPN_KEY_REALM);
    if (!realm.isEmpty()) {
        d->advUi.realm->setText(realm);
    }

    const QString samlPort = data.value(NM_OPENFORTIVPN_KEY_SAML_PORT);
    d->advUi.samlPort->setValue(samlPort.isEmpty() ? NM_OPENFORTIVPN_SAML_PORT_DEFAULT : samlPort.toInt());
    d->advUi.otpDelay->setValue(data.value(NM_OPENFORTIVPN_KEY_OTP_DELAY).toInt());
    d->advUi.persistent->setValue(data.value(NM_OPENFORTIVPN_KEY_PERSISTENT).toInt());

    const int minTls = d->advUi.minTls->findText(data.value(NM_OPENFORTIVPN_KEY_MIN_TLS));
    d->advUi.minTls->setCurrentIndex(qMax(minTls, 0));

    for (const auto &o : boolOpts) {
        const QString v = data.value(QLatin1String(o.key));
        // mesmos valores que o serviço aceita (insecure-ssl antigo era "yes")
        (d->advUi.*o.box)->setChecked(v.isEmpty() ? o.def : QStringList{QStringLiteral("1"), QStringLiteral("yes"), QStringLiteral("true"), QStringLiteral("on")}.contains(v));
    }
    for (const auto &o : textOpts) {
        (d->advUi.*o.edit)->setText(data.value(QLatin1String(o.key)));
    }
    for (const auto &o : urlOpts) {
        const QString v = data.value(QLatin1String(o.key));
        if (!v.isEmpty()) {
            (d->advUi.*o.edit)->setUrl(QUrl::fromLocalFile(v));
        }
    }

    d->advUi.pemPassphrase->setPasswordOption(optionFromFlags(data.value(NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE "-flags").toInt()));

    loadSecrets(setting);
}

void OpenfortivpnWidget::loadSecrets(const NetworkManager::Setting::Ptr &setting)
{
    Q_D(OpenfortivpnWidget);

    NetworkManager::VpnSetting::Ptr vpnSetting = setting.staticCast<NetworkManager::VpnSetting>();

    if (vpnSetting) {
        const NMStringMap secrets = vpnSetting->secrets();

        const QString password = secrets.value(NM_OPENFORTIVPN_KEY_PASSWORD);
        if (!password.isEmpty()) {
            d->ui.password->setText(password);
        }

        const QString pem = secrets.value(NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE);
        if (!pem.isEmpty()) {
            d->advUi.pemPassphrase->setText(pem);
        }
    }
}

QVariantMap OpenfortivpnWidget::setting() const
{
    Q_D(const OpenfortivpnWidget);

    NetworkManager::VpnSetting setting;
    setting.setServiceType(QLatin1String(NM_DBUS_SERVICE_OPENFORTIVPN));
    NMStringMap data;
    NMStringMap secrets;

    data.insert(NM_OPENFORTIVPN_KEY_GATEWAY, d->ui.gateway->text());

    if (!d->ui.username->text().isEmpty()) {
        data.insert(NM_OPENFORTIVPN_KEY_USER, d->ui.username->text());
    }

    if (!d->ui.password->text().isEmpty()) {
        secrets.insert(NM_OPENFORTIVPN_KEY_PASSWORD, d->ui.password->text());
    }

    if (d->ui.password->passwordOption() == PasswordField::StoreForAllUsers) {
        data.insert(NM_OPENFORTIVPN_KEY_PASSWORD "-flags", QString::number(NetworkManager::Setting::None));
    } else if (d->ui.password->passwordOption() == PasswordField::StoreForUser) {
        data.insert(NM_OPENFORTIVPN_KEY_PASSWORD "-flags", QString::number(NetworkManager::Setting::AgentOwned));
    } else if (d->ui.password->passwordOption() == PasswordField::AlwaysAsk) {
        data.insert(NM_OPENFORTIVPN_KEY_PASSWORD "-flags", QString::number(NetworkManager::Setting::NotSaved));
    } else {
        data.insert(NM_OPENFORTIVPN_KEY_PASSWORD "-flags", QString::number(NetworkManager::Setting::NotRequired));
    }

    if (!d->ui.caCert->url().isEmpty()) {
        data.insert(NM_OPENFORTIVPN_KEY_CA, d->ui.caCert->url().toLocalFile());
    }

    if (!d->ui.userCert->url().isEmpty()) {
        data.insert(NM_OPENFORTIVPN_KEY_CERT, d->ui.userCert->url().toLocalFile());
    }

    if (!d->ui.userKey->url().isEmpty()) {
        data.insert(NM_OPENFORTIVPN_KEY_KEY, d->ui.userKey->url().toLocalFile());
    }

    // From advanced
    if (!d->advUi.trustedCert->text().isEmpty()) {
        data.insert(NM_OPENFORTIVPN_KEY_TRUSTED_CERT, d->advUi.trustedCert->text());
    }

    if (d->advUi.otp->isChecked()) {
        data.insert(QLatin1String(NM_OPENFORTIVPN_KEY_OTP "-flags"), QString::number(NetworkManager::Setting::NotSaved));
    } else {
        data.insert(QLatin1String(NM_OPENFORTIVPN_KEY_OTP "-flags"), QString::number(NetworkManager::Setting::None));
    }

    if (d->advUi.tfa->isChecked()) {
        data.insert(QLatin1String(NM_OPENFORTIVPN_KEY_2FA "-flags"), QString::number(NetworkManager::Setting::AgentOwned));
        data.insert(QLatin1String(NM_OPENFORTIVPN_KEY_OTP "-flags"), QString::number(NetworkManager::Setting::None));
    }

    if (d->advUi.saml->isChecked()) {
        data.insert(NM_OPENFORTIVPN_KEY_SAML_LOGIN, QLatin1String("true"));
    } else {
        data.insert(NM_OPENFORTIVPN_KEY_SAML_LOGIN, QLatin1String("false"));
    }

    if (!d->advUi.realm->text().isEmpty()) {
        data.insert(NM_OPENFORTIVPN_KEY_REALM, d->advUi.realm->text());
    }

    const int samlPort = d->advUi.samlPort->value();
    if (samlPort != NM_OPENFORTIVPN_SAML_PORT_DEFAULT) {
        data.insert(NM_OPENFORTIVPN_KEY_SAML_PORT, QString::number(samlPort));
    }
    if (d->advUi.otpDelay->value() != 0) {
        data.insert(NM_OPENFORTIVPN_KEY_OTP_DELAY, QString::number(d->advUi.otpDelay->value()));
    }
    if (d->advUi.persistent->value() != 0) {
        data.insert(NM_OPENFORTIVPN_KEY_PERSISTENT, QString::number(d->advUi.persistent->value()));
    }
    if (d->advUi.minTls->currentIndex() > 0) {
        data.insert(NM_OPENFORTIVPN_KEY_MIN_TLS, d->advUi.minTls->currentText());
    }
    for (const auto &o : boolOpts) {
        if ((d->advUi.*o.box)->isChecked() != o.def) {
            data.insert(QLatin1String(o.key), (d->advUi.*o.box)->isChecked() ? QStringLiteral("1") : QStringLiteral("0"));
        }
    }
    for (const auto &o : textOpts) {
        const QString v = (d->advUi.*o.edit)->text();
        if (!v.isEmpty()) {
            data.insert(QLatin1String(o.key), v);
        }
    }
    for (const auto &o : urlOpts) {
        const QUrl u = (d->advUi.*o.edit)->url();
        if (!u.isEmpty()) {
            data.insert(QLatin1String(o.key), u.toLocalFile());
        }
    }

    if (!d->advUi.pemPassphrase->text().isEmpty()) {
        secrets.insert(NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE, d->advUi.pemPassphrase->text());
    }
    data.insert(NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE "-flags", QString::number(flagsFromOption(d->advUi.pemPassphrase->passwordOption())));

    setting.setData(data);
    setting.setSecrets(secrets);

    return setting.toMap();
}

void OpenfortivpnWidget::showAdvanced()
{
    Q_D(OpenfortivpnWidget);

    d->advancedDlg->show();
}

bool OpenfortivpnWidget::isValid() const
{
    Q_D(const OpenfortivpnWidget);

    return !d->ui.gateway->text().isEmpty();
}

#include "moc_openfortivpnwidget.cpp"
