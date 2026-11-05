import gzip
import json
import struct

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter, affine_transform

from backend.volume_preview import encode_volume, preview_affine


def write_volume(tmp_path, shape=(3,4,5), affine=None):
    affine=np.diag([3.,3.,3.,1.]) if affine is None else affine
    data=np.arange(np.prod(shape),dtype=np.float32).reshape(shape)
    for kind in ['ct','pet']:np.save(tmp_path/f'preview_{kind}.npy',data)
    meta={'preview_shape_xyz':list(shape),'preview_spacing_mm':[3.,3.,3.],
          'output_shape_xyz':list(shape),'output_affine_RAS_mm':affine.tolist(),
          'preview_affine_RAS_mm':affine.tolist()}
    (tmp_path/'metadata.json').write_text(json.dumps(meta))
    return data,meta


def decode(payload):
    raw=gzip.decompress(payload);size=struct.unpack('<I',raw[:4])[0]
    meta=json.loads(raw[4:4+size]);assert size%4==0
    array=np.frombuffer(raw[4+size:],dtype='<f4').reshape(meta['dimensions'],order='F')
    return meta,array


def test_voxel_order_and_ras_to_lps_preserve_landmarks(tmp_path):
    affine=np.diag([3.,3.,3.,1.]);affine[:3,3]=[24,-50,80]
    data,meta=write_volume(tmp_path,affine=affine)
    header,restored=decode(encode_volume(tmp_path,'ct'))
    np.testing.assert_array_equal(restored,data)
    direction=np.asarray(header['direction']).reshape(3,3,order='F')
    for point in [[0,0,0],[1,2,3],[2,3,4]]:
        world=np.asarray(header['origin'])+direction@(np.asarray(point)*header['spacing'])
        np.testing.assert_allclose(world,(np.diag([-1,-1,1,1])@affine@[*point,1])[:3])
    assert header['units']=='HU'
    pet,_=decode(encode_volume(tmp_path,'pet'));assert pet['units']=='model_raw_not_SUV'
    assert pet['origin']==header['origin']


def test_decimation_has_shared_geometry_and_bounded_payload(tmp_path):
    data,_=write_volume(tmp_path,(321,5,6))
    ct,array=decode(encode_volume(tmp_path,'ct'));pet,_=decode(encode_volume(tmp_path,'pet'))
    assert max(ct['dimensions'])<=160
    assert ct['decimation']==320/159
    np.testing.assert_allclose(ct['spacing'],[3*320/159]*3)
    assert ct['dimensions'][0]==160
    assert ct['dimensions']==pet['dimensions']
    np.testing.assert_allclose(array,affine_transform(gaussian_filter(data, sigma=ct["decimation"]/2, mode="nearest"), np.eye(3)*ct["decimation"], output_shape=ct["dimensions"], order=1, mode="nearest", prefilter=False))
    assert ct["antialias"] and pet["antialias"]


def test_legacy_preview_origin_matches_axis_aligned_resampling(tmp_path):
    affine=np.diag([-2.,-4.,3.,1.]);affine[:3,3]=[40,60,20]
    _,meta=write_volume(tmp_path,affine=affine);meta.pop('preview_affine_RAS_mm')
    result=preview_affine(meta)
    np.testing.assert_allclose(result[:3,3],[36,48,20])
    np.testing.assert_allclose(np.diag(result),[3,3,3,1])


def test_aliasing_is_suppressed_without_changing_saved_volume(tmp_path):
    data,_=write_volume(tmp_path,(322,5,6))
    data[:]=np.arange(322)[:,None,None]%2
    np.save(tmp_path/'preview_ct.npy',data)
    header,result=decode(encode_volume(tmp_path,'ct'))
    assert np.ptp(result[3:-3,0,0]) < .05
    np.testing.assert_array_equal(np.load(tmp_path/'preview_ct.npy'),data)
    assert header['origin']==[0,0,0]


def test_sheared_grid_rejected(tmp_path):
    affine=np.eye(4);affine[0,1]=.3
    write_volume(tmp_path,affine=affine)
    with pytest.raises(ValueError,match='Sheared'):
        encode_volume(tmp_path,'ct')


def test_small_overflow_does_not_halve_resolution(tmp_path):
    write_volume(tmp_path,(161,100,80))
    meta,_=decode(encode_volume(tmp_path,'ct'))
    assert meta['dimensions']==[160,99,79]
    assert 3 < meta['spacing'][0] < 3.1
