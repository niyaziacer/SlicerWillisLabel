cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)
project(WillisLabel)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/niyaziacer/SlicerWillisLabel")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Niyazi Acer")
set(EXTENSION_DESCRIPTION "Extracts intracranial arteries from TOF-MRA and labels them anatomically (vertebral, basilar, internal carotid, cerebellar arteries and the circle of Willis segments A1, AComA, A2, P1, PComA, P2, MCA) from one seed point per artery, colouring each branch from its origin and exporting one STL per artery.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/niyaziacer/SlicerWillisLabel/main/WillisLabel/Resources/Icons/WillisLabel.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/niyaziacer/SlicerWillisLabel/main/Screenshots/Screenshot1.png")
set(EXTENSION_DEPENDS "NA")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(WillisLabel)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
