# TopCoW (DKFZ, TopCoW 2024) modelini Docker ile çalıştırır ve sonucu Willis Label'a yükler.
#
# Kullanım (Slicer Python konsolunda, Willis Label modülünde TOF görüntüsü seçiliyken):
#   exec(open(r"C:\...\SlicerWillisLabel\Docs\topcow_calistir.py", encoding="utf-8").read())
#
# Gereksinimler: Docker Desktop çalışır durumda, model imajı yüklenmiş
#   (docker image load -i Team_DKFZ_topcow_seg.tar.gz  ->  topcow24_ct:latest)
# Atıf: TopCoW challenge paper, arXiv:2312.17670

import os
import shutil
import subprocess
import time

import qt
import SimpleITK as sitk
import sitkUtils
import slicer

DOCKER_IMAGE = "topcow24_ct:latest"
USE_GPU = True          # NVIDIA GPU yoksa False yapın (GPU'suz çalışma denenmedi)

w = slicer.modules.willislabel.widgetRepresentation().self()
vol = w.inputSelector.currentNode()
if vol is None:
    raise RuntimeError("Önce Willis Label modülünde 'TOF volume' seçin.")

work = os.path.join(os.path.expanduser("~"), "WillisLabel_TopCoW", vol.GetName())
indir, outdir = os.path.join(work, "in"), os.path.join(work, "out")
shutil.rmtree(work, ignore_errors=True)
for sub in ("head-mr-angio", "head-ct-angio"):
    os.makedirs(os.path.join(indir, "images", sub))
os.makedirs(outdir)

# Model girdiyi LPS+ yönelimde istiyor
img = sitk.DICOMOrient(sitkUtils.PullVolumeFromSlicer(vol), "LPS")
for sub in ("head-mr-angio", "head-ct-angio"):
    sitk.WriteImage(img, os.path.join(indir, "images", sub, "tof.nii.gz"))

cmd = ["docker", "run", "--rm", "--network", "none", "--shm-size=8g"]
if USE_GPU:
    cmd += ["--gpus", "all"]
cmd += ["-v", f"{indir}:/input:ro", "-v", f"{outdir}:/output", DOCKER_IMAGE]

print("TopCoW çalışıyor, Slicer birkaç dakika donmuş görünebilir...")
t0 = time.time()
slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
try:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
finally:
    slicer.app.restoreOverrideCursor()

result = os.path.join(outdir, "images", "cow-multiclass-segmentation", "output.mha")
if not os.path.exists(result):
    print(r.stdout[-2000:])
    print(r.stderr[-2000:])
    raise RuntimeError("TopCoW çıktı üretmedi; yukarıdaki hata mesajına bakın.")

# Sonucu TOF dosyasının yanına "<ad>_TopCoW.mha" olarak da kopyala (sonra kolayca bulunsun)
sn = vol.GetStorageNode()
tof_dir = os.path.dirname(sn.GetFileName()) if sn and sn.GetFileName() else os.path.join(os.path.expanduser("~"), "Desktop")
kopya = os.path.join(tof_dir, vol.GetName() + "_TopCoW.mha")
try:
    shutil.copyfile(result, kopya)
    print("TopCoW sonucu kaydedildi:", kopya)
except OSError as e:
    print("TopCoW sonucu TOF klasörüne kopyalanamadı:", e)

lab = slicer.util.loadLabelVolume(result)
lab.SetName(vol.GetName() + "_TopCoW")
w.topcowSelector.setCurrentNode(lab)
print(f"TopCoW tamamlandı ({time.time() - t0:.0f} s). '{lab.GetName()}' TopCoW labels olarak seçildi.")
