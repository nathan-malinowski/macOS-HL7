# Third-Party Licenses

macOS-HL7 is distributed under the MIT License (see [LICENSE](LICENSE)) and
depends on the following third-party components. Their license texts are
included in the built `.app` bundle under
`Contents/Resources/lib/python*/site-packages/<package>/`.

| Package  | Version  | License   | Project URL                                 |
|----------|----------|-----------|---------------------------------------------|
| PySide6  | ≥ 6.6    | LGPL-3.0  | https://wiki.qt.io/Qt_for_Python            |
| hl7apy   | ≥ 1.3.5  | MIT       | https://github.com/crs4/hl7apy              |
| PyYAML   | ≥ 6.0    | MIT       | https://github.com/yaml/pyyaml              |

## LGPL-3.0 notice for PySide6

PySide6 (and the underlying Qt libraries) are licensed under the GNU Lesser
General Public License v3.0. This project links to PySide6 dynamically via
Python's `import` machinery, which satisfies the LGPL's "any use" relinking
requirement. The full LGPL text is bundled with the PySide6 distribution at
`Contents/Resources/lib/python*/site-packages/PySide6/LICENSE.LGPLv3`.

To exercise your LGPL rights, you may replace the bundled PySide6 with a
modified build by substituting the files under
`macOS-HL7.app/Contents/Resources/lib/python*/site-packages/PySide6/`.

## MIT notices

The MIT licenses for `hl7apy` and `PyYAML` are included verbatim in each
package's source directory inside the `.app` bundle. No modification has been
made to either project.

## py2app (build-time only)

`py2app` is used to produce the `.app` bundle but is not redistributed as part
of the bundle. It is licensed under the PSF-style license:
https://github.com/ronaldoussoren/py2app/blob/master/LICENSE.txt
