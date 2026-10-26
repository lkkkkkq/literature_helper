; Use electron-builder's external-package layout without a network downloader.
; Missing or mismatched local payloads abort before any installation is attempted.
!macro customInit
  IfFileExists "$EXEDIR\${APP_64_NAME}" +3 0
    MessageBox MB_OK|MB_ICONSTOP "Please keep this installer and ${APP_64_NAME} in the same folder." /SD IDOK
    Abort
  ${StdUtils.HashFile} $0 "SHA2-512" "$EXEDIR\${APP_64_NAME}"
  StrCmp $0 "${APP_64_HASH}" +3 0
    MessageBox MB_OK|MB_ICONSTOP "The local LitExtract data package is damaged or belongs to another release. Please copy both release files again." /SD IDOK
    Abort
!macroend

; The upstream web layout moves the payload into its update cache. Keep a copy
; beside the offline setup so users can pass the same two files to another tester.
!macro customInstall
  IfFileExists "$EXEDIR\${APP_64_NAME}" litextract_payload_kept 0
    CopyFiles /SILENT "$LOCALAPPDATA\${APP_PACKAGE_STORE_FILE}" "$EXEDIR\${APP_64_NAME}"
  litextract_payload_kept:
!macroend
