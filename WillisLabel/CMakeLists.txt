set(MODULE_NAME WillisLabel)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  WillisLabelLib/__init__.py
  WillisLabelLib/aca.py
  WillisLabelLib/anatomy.py
  WillisLabelLib/branches.py
  WillisLabelLib/core.py
  WillisLabelLib/sca.py
  WillisLabelLib/topcow.py
  WillisLabelLib/topcow_infer.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/${MODULE_NAME}.png
  )

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )
