set(MODULE_NAME WillisLabel)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  WillisLabelLib/__init__.py
  WillisLabelLib/core.py
  WillisLabelLib/anatomy.py
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
