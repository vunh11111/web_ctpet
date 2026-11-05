from io import BytesIO
from pathlib import Path
import zipfile
import nibabel as nib
import numpy as np
from PIL import Image
import pytest
from common.archive import InputError, extract_archive, inspect_archive
from model_service.preview import render
from model_service.volumes import load_volume


def test_zip_path_traversal_and_windows_paths_are_rejected(tmp_path):
    for name in ('../outside.txt', '/tmp/outside.txt', 'C:\\outside.txt', 'safe/../../outside.txt'):
        path=tmp_path/'input.zip'
        with zipfile.ZipFile(path,'w') as archive: archive.writestr(name,'bad')
        with pytest.raises(InputError): extract_archive(path,tmp_path/'output',1024)
    assert not (tmp_path/'outside.txt').exists()


def test_archive_size_and_duplicate_names_are_rejected(tmp_path):
    path=tmp_path/'input.zip'
    with zipfile.ZipFile(path,'w') as archive: archive.writestr('ct.dcm','a'*100)
    with pytest.raises(InputError): inspect_archive(path,50)
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('CT.dcm','a'); archive.writestr('ct.dcm','b')
    with pytest.raises(InputError): inspect_archive(path,1024)


def test_nifti_geometry_is_preserved_in_canonical_space(tmp_path):
    data=np.arange(8*9*10,dtype=np.float32).reshape(8,9,10)
    affine=np.diag([-2.,-3.,4.,1.]);affine[:3,3]=[20,30,40]
    source=nib.Nifti1Image(data,affine)
    nib.save(source,tmp_path/'ct.nii.gz')
    result,meta=load_volume(tmp_path,10000)
    expected=nib.as_closest_canonical(source)
    assert meta['input_format']=='NIfTI'
    np.testing.assert_array_equal(result.get_fdata(),expected.get_fdata())
    np.testing.assert_allclose(result.affine,expected.affine)


def test_multiple_niftis_and_nonfinite_voxels_fail(tmp_path):
    for name in ['a.nii.gz','b.nii.gz']:
        nib.save(nib.Nifti1Image(np.zeros((3,4,5),np.float32),np.eye(4)),tmp_path/name)
    with pytest.raises(InputError,match='nhiều'): load_volume(tmp_path,10000)
    (tmp_path/'b.nii.gz').unlink()
    data=np.zeros((3,4,5),np.float32);data[0,0,0]=np.nan
    nib.save(nib.Nifti1Image(data,np.eye(4)),tmp_path/'a.nii.gz')
    with pytest.raises(InputError):load_volume(tmp_path,10000)


def test_preview_slices_use_shared_axes_and_correct_orientation(tmp_path):
    x,y,z=np.indices((3,4,5));data=(20*x+5*y+z).astype(np.float32)
    np.save(tmp_path/'preview_ct.npy',data);np.save(tmp_path/'preview_pet.npy',data)
    for plane,axis in [('axial',2),('coronal',1),('sagittal',0)]:
        png=render(tmp_path,'ct',plane,1,'soft',12000)
        pixels=np.asarray(Image.open(BytesIO(png)))
        expected=(np.clip((np.take(data,1,axis=axis).T[::-1]+160)/400,0,1)*255).astype(np.uint8)
        np.testing.assert_array_equal(pixels[:,:,0],expected)
        pet=Image.open(BytesIO(render(tmp_path,'pet',plane,1,'soft',12000)))
        assert pet.size==(pixels.shape[1],pixels.shape[0])
    with pytest.raises(InputError):render(tmp_path,'ct','axial',99,'soft',12000)


def test_dicom_intercept_is_applied_once(tmp_path):
    from scripts.make_test_ct import make_dicom
    folder=tmp_path/'dicom';make_dicom(folder)
    result,meta=load_volume(folder,100000)
    assert meta['input_format']=='DICOM'
    assert nib.aff2axcodes(result.affine)==('R','A','S')
    values=result.get_fdata()
    assert values.min()==-1000
    assert values.max()==700
    np.testing.assert_allclose(np.linalg.norm(result.affine[:3,:3],axis=0),[3,3,3])


def test_mixed_dicom_ignores_secondary_capture_and_requires_series_choice(tmp_path):
    import pydicom
    from pydicom.uid import SecondaryCaptureImageStorage, generate_uid
    from scripts.make_test_ct import make_dicom
    from model_service.volumes import SeriesSelectionRequired
    first, second = tmp_path/'first', tmp_path/'second'
    make_dicom(first); make_dicom(second)
    source = pydicom.dcmread(next(first.glob('*.dcm')))
    source.SOPClassUID = SecondaryCaptureImageStorage
    source.file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    source.SOPInstanceUID = generate_uid()
    source.file_meta.MediaStorageSOPInstanceUID = source.SOPInstanceUID
    for tag in ['ImagePositionPatient','ImageOrientationPatient','PixelSpacing']:
        delattr(source,tag)
    source.save_as(tmp_path/'screenshot.dcm',enforce_file_format=True)
    source.Modality='PT';source.save_as(tmp_path/'pet.dcm',enforce_file_format=True)
    with pytest.raises(SeriesSelectionRequired) as caught:
        load_volume(tmp_path,100000)
    assert sorted(o['slices'] for o in caught.value.options)==[16,16]
    assert caught.value.ignored==2
    for option in caught.value.options:
        result,meta=load_volume(tmp_path,100000,option['uid'])
        assert meta['selected_series_uid']==option['uid']
        assert meta['ignored_files']==2
        assert result.get_fdata().min()==-1000
        assert result.get_fdata().max()==700
    with pytest.raises(InputError,match='không tồn tại'):
        load_volume(tmp_path,100000,'not-an-existing-series')


def test_missing_geometry_in_real_ct_still_fails(tmp_path):
    import pydicom
    from scripts.make_test_ct import make_dicom
    make_dicom(tmp_path)
    path=next(tmp_path.glob('*.dcm'));ds=pydicom.dcmread(path)
    del ds.ImagePositionPatient
    ds.save_as(path,enforce_file_format=True)
    with pytest.raises(InputError,match='thiếu thông tin'):
        load_volume(tmp_path,100000)
