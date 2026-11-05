"""Generate small, entirely synthetic CTs for functional QA, not patient data."""
from pathlib import Path
import zipfile
import nibabel as nib
import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid


def phantom():
    x,y,z=np.indices((40,48,16));image=np.full((40,48,16),-1000,dtype=np.int16)
    body=((x-20)/15)**2+((y-24)/19)**2<1
    image[body]=40
    image[((x-20)**2+(y-29)**2<14)]=700
    image[((x-12)**2+(y-22)**2<12)]=90
    return image


def make_dicom(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    image=phantom();series,study,frame=generate_uid(),generate_uid(),generate_uid()
    for z in range(image.shape[2]):
        meta=FileMetaDataset();meta.MediaStorageSOPClassUID=CTImageStorage
        meta.MediaStorageSOPInstanceUID=generate_uid();meta.TransferSyntaxUID=ExplicitVRLittleEndian
        path=folder/f'{z:03}.dcm';ds=FileDataset(str(path),{},file_meta=meta,preamble=b'\0'*128)
        ds.SOPClassUID=CTImageStorage;ds.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
        ds.Modality='CT';ds.SeriesInstanceUID=series;ds.StudyInstanceUID=study;ds.FrameOfReferenceUID=frame
        ds.PatientName='QA^PHANTOM';ds.PatientID='SYNTHETIC';ds.SeriesNumber=1;ds.InstanceNumber=z+1
        ds.ImageType=['ORIGINAL','PRIMARY','AXIAL'];ds.ImagePositionPatient=[0,0,z*3]
        ds.ImageOrientationPatient=[1,0,0,0,1,0];ds.PixelSpacing=[3,3];ds.SliceThickness=3
        pixels=(image[:,:,z].T.astype(np.int32)+8192).astype(np.uint16)
        ds.Rows,ds.Columns=pixels.shape;ds.SamplesPerPixel=1;ds.PhotometricInterpretation='MONOCHROME2'
        ds.BitsAllocated=16;ds.BitsStored=16;ds.HighBit=15;ds.PixelRepresentation=0
        ds.RescaleSlope=1;ds.RescaleIntercept=-8192;ds.RescaleType='HU';ds.PixelData=pixels.tobytes()
        ds.save_as(path,enforce_file_format=True)


def main():
    root=Path(__file__).resolve().parents[1]/'data'/'qa'
    root.mkdir(parents=True,exist_ok=True)
    image=nib.Nifti1Image(phantom().astype(np.float32),np.diag([3.,3.,3.,1.]))
    image.header.set_xyzt_units('mm');nib.save(image,root/'ct.nii.gz')
    with zipfile.ZipFile(root/'ct_nifti.zip','w',compression=zipfile.ZIP_DEFLATED) as z:z.write(root/'ct.nii.gz','ct.nii.gz')
    make_dicom(root/'dicom')
    with zipfile.ZipFile(root/'ct_dicom.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for file in (root/'dicom').glob('*.dcm'):z.write(file,f'CT/{file.name}')
    with zipfile.ZipFile(root/'invalid_ct.zip','w') as z:z.writestr('readme.txt','No CT in this archive')
    print('Created synthetic NIfTI/DICOM ZIPs in data/qa (not patient data).')


if __name__=='__main__':main()
