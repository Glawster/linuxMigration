#!/usr/bin/env bash
# Launch digiKam with the Qt/KDE file dialog instead of the GTK one

export QT_QPA_PLATFORMTHEME=qt5ct
exec digikam "$@"

