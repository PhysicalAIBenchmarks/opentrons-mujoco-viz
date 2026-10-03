# Namespace shim — extends the opentrons package namespace so that
# `from opentrons.visualization import WetLabScene` works whether or not
# the full `opentrons` pip package is installed alongside this one.
#
# When upstreamed to Opentrons/opentrons, this file is replaced by opentrons'
# own __init__.py and opentrons/visualization/ lives directly inside that repo.
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
