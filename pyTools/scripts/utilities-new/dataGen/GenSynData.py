#!/usr/bin/python
"""
This script extracts the target features from the *.htk generated by CURRENNT.
Note that this script relies on the data_config.py for the test data
"""

import numpy as np
import sys, os
import scipy
from   scipy import io

try:
    from binaryTools import readwriteC2 as funcs
except ImportError:
    try:
        from binaryTools import readwriteC2_220 as funcs
    except ImportError:
        try: 
            from ioTools import readwrite as funcs
        finally:
            print "Please add pyTools to PYTHONPATH"
            raise Exception("Can't not import binaryTools/readwriteC2 or ioTools/readwrite")

from speechTools import discreteF0 as f0funcs
            

sys.path.append(os.path.dirname(sys.argv[1]))
cfg = __import__(os.path.basename(sys.argv[1]).split('.')[0])


def defaultOutput(dataOut, outname):
    """ Default output interface
    """
    funcs.write_raw_mat(dataOut, outname)

def f0Conversion(dataOut, outname):
    """ Convert the discrete F0 into continuous F0, if the data is lf0
    """
    fileDir           = os.path.dirname(outname)
    fileName          = os.path.basename(outname)
    fileBase, fileExt = os.path.splitext(fileName)

    if fileExt == '.qf0' or fileExt == '.lf0':
        # for F0
        f0Max, f0Min, f0Levels, f0Interpolated   = cfg.f0Info

        defaultOutput(dataOut, fileDir + os.path.sep + fileBase + '.qf0')
        
        dataOut, vuv = f0funcs.f0Conversion(dataOut, f0Max, f0Min, f0Levels, 'd2c', f0Interpolated)
        if f0Interpolated:
            vuvFile  = fileDir + os.path.sep + fileBase + '.vuv'
            if os.path.isfile(vuvFile):
                vuv  = funcs.read_raw_mat(vuvFile, 1)
                dataOut[vuv<0.5] = 0.0
            else:
                print "Can't find %s for interpolated F0" % (vuvFile)
        
        # if the extension is .qf0 (quantized F0)
        defaultOutput(vuv, fileDir + os.path.sep + fileBase + '.vuv')
        defaultOutput(dataOut, fileDir + os.path.sep + fileBase + '.lf0')

    else:
        # for other data
        defaultOutput(dataOut, outname)
    
    

def SplitData(fileScp,      fileDir2,   fileDir, 
              outputName,   outDim,     outputDelta, 
              datamv,     normMask,
              outputMethod,
              stdT=0.000001):
    """ Split the generated HTK into acoustic features
    """
    
    filePtr = open(fileDir+os.path.sep+'gen.scp', 'w')
    
    if len(datamv) > 0 and os.path.isfile(datamv):
        print "External Mean Variance file will be used to de-normalize the data"
        try:
            datamv    = io.netcdf_file(datamv)
            m         = datamv.variables['outputMeans'][:].copy()
            v         = datamv.variables['outputStdevs'][:].copy()
            assert m.shape[0]==sum(outDim), "Incompatible dimension"
        except TypeError:
            datamv    = funcs.read_raw_mat(datamv, 1)
            assert datamv.shape[0] == sum(outDim)*2, 'Dim of datamv is invalid'
            m         = datamv[0:sum(outDim)]
            v         = datamv[sum(outDim):sum(outDim)*2]
        v[v<stdT] = 1.0
        if normMask is not None:
            assert normMask.shape[0] == m.shape[0], 'normMask dimension invalid'
            m = m * normMask
            v = v ** normMask
    else:
        m = np.zeros([sum(outDim)])
        v = np.ones([sum(outDim)])
    
    for fileName in fileScp:
        fileBaseName, fileExt = os.path.splitext(fileName)
        
        if os.path.isfile(fileDir2 + os.path.sep + fileName) and fileExt=='.htk':
            filePtr.write(fileDir2+os.path.sep+fileName+'\n')

            # the output of CURRENNT is big-endian
            data = funcs.read_htk(fileDir2 + os.path.sep + fileName, end='b')
            assert data.shape[1]==sum(outDim), "Dimension of "+ fileName +" != "+ str(sum(outDim))
            data = data*v+m

            # extract the data from the htk output of CURRENNT 
            for index, outname in enumerate(outputName):
                sIndex = sum(outDim[:index])
                eIndex = sum(outDim[:index+1])

                # generate both delta and static components
                if outputDelta[index]>1:

                    # output static component
                    staticIndex = sIndex + (eIndex-sIndex)/outputDelta[index]
                    outname = outname.split('_delta')[0]
                    dataOut = data[:, sIndex:staticIndex]
                    outname = fileDir + os.path.sep + fileBaseName + os.path.extsep + outname
                    outputMethod(dataOut, outname)

                    # output all 
                    outname = outname + '_delta'
                    dataOut = data[:, sIndex:eIndex]
                    outputMethod(dataOut, outname)
                    
                else:
                    # feature don't have delta component
                    outname = outname.split('_delta')[0]	
                    dataOut = data[:, sIndex:eIndex]
                    outname = fileDir + os.path.sep + fileBaseName + os.path.extsep + outname
                    outputMethod(dataOut, outname)
                    
            print "Writing acoustic data: "+ fileBaseName
            
        elif fileExt=='.htk':
            print "Cannot find file %s" + fileName
            
    filePtr.close()

def normMaskGen1(inDim, outDim, normMask):
    """ Generating the normMask for packaging the data
    """
    assert len(inDim)+len(outDim)==len(normMask), "Unequal length normMask and inDim outDim"
    inDim = np.array(inDim)
    outDim = np.array(outDim)
    dimAll = np.concatenate((inDim, outDim))
    
    dimVec = np.ones([dimAll.sum()])
    dimS = 0
    for idx, dim in enumerate(normMask):
        if len(dim)==2:
            # [start end] 
            nS, nE = dim[0] + dimS, dim[1] + dimS
            assert nS>=dimS, "Please check normMask, %s cannot be handled" % (str(dim))
            assert nE<=(dimS+dimAll[idx]),"Please check normMask, %s cannot be handled" % (str(dim))
            dimVec[nS:nE] = 0
        elif len(dim)==1 and dim[0]==0:
            # [0] all to zero
            dimVec[dimS:(dimS+dimAll[idx])] = 0
        else:
            # nothing []
            pass
        dimS = dimS + dimAll[idx]
    
    return dimVec[inDim.sum():]


if __name__ == "__main__":
    """ Split the generated .htk into multiple files
    """
    try:
        outDim   = cfg.outFeatDim
    except AttributeError:
        outDim   = cfg.outDim
        
    outputName   = cfg.outputName
    outputDelta  = cfg.outputDelta
    fileDir      = sys.argv[2]
    
    
    # Additional operation
    if 'f0Info' in dir(cfg):
        print "Conversion on discrete F0 symbol"
        outputMethod = f0Conversion
    else:
        outputMethod = defaultOutput
    
    fileDir2 = sys.argv[3]
    
    if 'inMask' in dir(cfg) and 'outMask' in dir(cfg):
        assert len(cfg.outMask) == len(cfg.outputName), "outMask uncompatible"
        tempoutDim = []
        for dim in cfg.outMask:
            if len(dim)>0:
                tempoutDim.append(dim[1] - dim[0])
        if len(tempoutDim)>0:
            outDim = tempoutDim
            

    # Generating the normlization mask file
    if 'normMask' in dir(cfg):
        print "Generating normMask"
        normMask = normMaskGen1(cfg.inDim, cfg.outDim, cfg.normMask)
    else:
        normMask = None
                
    datamv = sys.argv[4]
    assert os.path.isdir(fileDir), "Cannot not find " + fileDir
    
    files  = os.listdir(fileDir2)
    assert len(outDim)==len(outputName), "Config error: outDim outputName dimension mismatch"
    assert len(outDim)==len(outputDelta),"Config error: outDim outputDelta dimension mismatch"
    
    SplitData(files, fileDir2, fileDir, outputName, 
              outDim, outputDelta, datamv, normMask, outputMethod)