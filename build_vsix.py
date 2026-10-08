#!/usr/bin/env python3
"""Package this folder as an installable .vsix without needing node/npm/vsce.

    python3 build_vsix.py            -> slurmboard-<version>.vsix and slurmboard.vsix

slurmboard.vsix is the same file under a fixed name, so the README's download button
(releases/latest/download/slurmboard.vsix) always gets the newest release.

README images use https://raw.githubusercontent.com links: VSCode's extension page
does not load images from the extension folder.
"""
import json
import os
import shutil
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["package.json", "extension.js", "slurmboard.py", "README.md", "LICENSE",
         "media/icon.svg", "media/icon.png"]


pkg = json.load(open(os.path.join(HERE, "package.json")))
out = os.path.join(HERE, "%s-%s.vsix" % (pkg["name"], pkg["version"]))

manifest = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}" />
    <DisplayName>{display}</DisplayName>
    <Description xml:space="preserve">{desc}</Description>
    <Categories>Other</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/media/icon.png" Addressable="true" />
  </Assets>
</PackageManifest>
""".format(name=pkg["name"], version=pkg["version"], publisher=pkg["publisher"],
           display=escape(pkg["displayName"]), desc=escape(pkg["description"]),
           engine=escape(pkg["engines"]["vscode"]))

content_types = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json" />
  <Default Extension=".js" ContentType="application/javascript" />
  <Default Extension=".py" ContentType="text/plain" />
  <Default Extension=".md" ContentType="text/markdown" />
  <Default Extension=".svg" ContentType="image/svg+xml" />
  <Default Extension=".png" ContentType="image/png" />
  <Default Extension=".vsixmanifest" ContentType="text/xml" />
  <Default Extension="" ContentType="text/plain" />
</Types>
"""

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("extension.vsixmanifest", manifest)
    z.writestr("[Content_Types].xml", content_types)
    for f in FILES:
        z.write(os.path.join(HERE, f), "extension/" + f)
print(out)
shutil.copyfile(out, os.path.join(HERE, "%s.vsix" % pkg["name"]))
