#! /usr/bin/env python
# coding=utf-8
#   =======================================================================
#
# Copyright (C) 2018, Hisilicon Technologies Co., Ltd. All Rights Reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   1 Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#
#   2 Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
#   3 Neither the names of the copyright holders nor the names of the
#   contributors may be used to endorse or promote products derived from this
#   software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#   =======================================================================
#
import os
import sys
import numpy as np
import copy

from hiaiapp.hiaiapp import *
from hiaiapp.image import *
from hiaiapp.dvpp import *
from hiaiapp.message import *
from hiaiapp.appgraph import *
from datatype import *
from datetime import *

import hiai

kModelWidth = 300  # face detection model input width
kModelHeight = 300  # face detection model input height

class FaceDetectionInference(AppEngine):
    def __init__(self, aiConfig):
        for item in aiConfig._ai_config_item:
            #get model path configuration from graph.config  
            if item._AIConfigItem__name == "model_path":
                self.modelPath = item._AIConfigItem__value
                print("model: ", self.modelPath)
                if os.path.exists(self.modelPath) == False:
                    raise Exception("Model file %s is not exist!"%(self.modelPath))
                break
        self.aiConfig = aiConfig
        #aligned flag is True, because for when transform the face detection caffe model to D model, we turn on AIPP
        self.isAligned = True
        self.first = True

    #Resize image from camera. when self.isAligned is true, the size of resize image is 384*304,
    #for width align with 128, height align with 16
    def ResizeImageOfFrame(self, srcFrame):
        resizedImgList = []
        for i in range(0, srcFrame.batchInfo.batchSize):
            srcImgParam = srcFrame.imageList[i]
            if srcImgParam.imageData.format != IMAGEFORMAT.YUV420SP:
                print("Resize image: input image type does not yuv420sp, notify camera stop")
                SetExitFlag(True)
                return HIAI_APP_ERROR

            resizedImg = ImageData()
            #model resolution, not image resolution
            modeResolution = Resolution(kModelWidth, kModelHeight)
            ret = ResizeImage(resizedImg, srcImgParam, modeResolution, self.isAligned)
            if ret != HIAI_APP_OK:
                print("Image resize error")
                continue
            resizedImgList.append(resizedImg)
        return resizedImgList
    
    #Convert the image(YUV) from camera to jpeg
    def ConvImageOfFrameToJpeg(self, srcFrame):
        jpegImgParamList = []
        for i in range(0, srcFrame.batchInfo.batchSize):
            srcImgParam = srcFrame.imageList[i]
            if srcImgParam.imageData.format != IMAGEFORMAT.YUV420SP:
                print("[InferenceEngine]Input image type does not match, notify camera stop")
                SetExitFlag(True)
                return HIAI_APP_ERROR, None

            jpegImgParam = NewImageParam()
            ret = ConvertImageYuvToJpeg(jpegImgParam, srcImgParam)
            if ret != HIAI_APP_OK:
                print("Convert YUV Image to Jpeg failed, notify camera stop")
                SetExitFlag(True)
                return HIAI_APP_ERROR, None
            jpegImgParamList.append(jpegImgParam)

        return HIAI_APP_OK, jpegImgParamList
    
    #Inference the image
    def ExcuteInference(self, images):
        result = []
        for i in range(0, len(images)):
            nArray = Yuv2Array(images[i])
            ssd = {"name": "face_detection", "path": self.modelPath}
            nntensor = hiai.NNTensor(nArray)
            tensorList = hiai.NNTensorList(nntensor)
            
            if self.first == True:
                
                self.graph = hiai.Graph(hiai.GraphConfig(graph_id=2001))
                with self.graph.as_default():
                    self.engine_config = hiai.EngineConfig(engine_name="HIAIDvppInferenceEngine",
                                                  side=hiai.HiaiPythonSide.Device,
                                                  internal_so_name='/lib/libhiai_python_device2.7.so',
                                                  engine_id=2001)
                    self.engine = hiai.Engine(self.engine_config)
                    self.ai_model_desc = hiai.AIModelDescription(name=ssd['name'], path=ssd['path'])
                    self.ai_config = hiai.AIConfig(hiai.AIConfigItem("Inference", "item_value_2"))
                    final_result = self.engine.inference(input_tensor_list=tensorList,
                                                ai_model=self.ai_model_desc,
                                                ai_config=self.ai_config)
                ret = copy.deepcopy(self.graph.create_graph())
                if ret != hiai.HiaiPythonStatust.HIAI_PYTHON_OK:
                    print("create graph failed, ret", ret)
                    d_ret = graph.destroy()
                    SetExitFlag(True)
                    return HIAI_APP_ERROR, None 
                self.first = False
            else:
                with self.graph.as_default():
                    final_result = self.engine.inference(input_tensor_list=tensorList,
                                                ai_model=self.ai_model_desc,
                                                ai_config=self.ai_config)
            resTensorList = self.graph.proc(input_nntensorlist=tensorList)
            print("Inference result: ", resTensorList[0].shape)
            result.append(resTensorList)
        return HIAI_APP_OK, result
    
    #The inference engine Entry
    def Process(self, data):
        if GetExitFlag() == True:
            print("Inference engine exit for exit flag be set")
            sys.exit(0)

        start = datetime.now()
        #Resize the image for inference
        resizedImgList = self.ResizeImageOfFrame(data)
        #Transform the image from camera to jpeg for presenter server display
        ret, jpegImgList = self.ConvImageOfFrameToJpeg(data)
        if ret != HIAI_APP_OK:
            raise Exception("Convert yuv image to jpeg failed")

        end = datetime.now() - start
        print("Image process  exhoust ", end.total_seconds())
        start - datetime.now()
        
        #The data send to post process engine
        transData = EngineTrans()
        transData.imageParamList = jpegImgList  #Image for persenter server to display
        transData.batchInfo = data.batchInfo
        transData.widthScale, transData.heightScale = AlignUpScaleRatio(kModelWidth, kModelHeight, self.isAligned)
        #Inference and detect face
        ret, outputTensorList = self.ExcuteInference(resizedImgList)
        if ret == HIAI_APP_OK:
            #Inference success
            transData.status = True
            transData.outputData = outputTensorList
        else:
            #Inference failed
            transData.status = False
            transData.msg = "HiAIInference Engine Process failed"
            print("Model inference return error")
        #Send inference data and jpeg image to post process engine
        SendData("EngineTrans", transData)
        end = datetime.now() - start
        print("model inference  exhoust ", end.total_seconds())

        return ret

