"""Synthetic multi-series CT export including a non-geometric screenshot."""
from pathlib import Path
import tempfile
import zipfile
import pydicom
from pydicom.uid import SecondaryCaptureImageStorage, generate_uid
from scripts.make_test_ct import make_dicom


def main():
    target=Path(__file__).resolve().parents[1]/'data/qa/ct_mixed_dicom.zip'
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for number,label in [(1,'CT QA chest'),(2,'CT QA abdomen')]:
            folder=root/f'CT{number}';make_dicom(folder)
            for path in folder.glob('*.dcm'):
                ds=pydicom.dcmread(path);ds.SeriesNumber=number;ds.SeriesDescription=label
                ds.save_as(path,enforce_file_format=True)
        ds=pydicom.dcmread(next((root/'CT1').glob('*.dcm')))
        ds.SOPClassUID=SecondaryCaptureImageStorage;ds.file_meta.MediaStorageSOPClassUID=SecondaryCaptureImageStorage
        ds.SOPInstanceUID=generate_uid();ds.file_meta.MediaStorageSOPInstanceUID=ds.SOPInstanceUID
        for tag in ['ImagePositionPatient','ImageOrientationPatient','PixelSpacing']:delattr(ds,tag)
        ds.save_as(root/'screenshot.dcm',enforce_file_format=True)
        ds.Modality='PT';ds.save_as(root/'pet.dcm',enforce_file_format=True)
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for path in root.rglob('*.dcm'):z.write(path,path.relative_to(root))
    print('Created synthetic mixed-series DICOM ZIP.')


if __name__=='__main__':main()
