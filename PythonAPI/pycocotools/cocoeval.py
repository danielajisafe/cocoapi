__author__ = 'tsungyi'

import numpy as np
import datetime
import time
from collections import defaultdict
from . import mask as maskUtils
import copy
import torch
from IPython import display
#from datetime import datetime

_F_PCK_SCORE1, _F_PCK_SCORE2,_F_PCK_SCORE = 0,0,0
_F_PCK_SCORE1_500, _F_PCK_SCORE1_1k = 0,0
_F_PCK_SCORE2_500, _F_PCK_SCORE2_1k = 0,0

_BEST_3D_PRED_POSES = []
all_cnt = 0
cnt = 0

print('*************** Pycoco cocoeval script (Can I see UPDATE on GCP??) *****************')
class COCOeval:
    # Interface for evaluating detection on the Microsoft COCO dataset.
    #
    # The usage for CocoEval is as follows:
    #  cocoGt=..., cocoDt=...       # load dataset and results
    #  E = CocoEval(cocoGt,cocoDt); # initialize CocoEval object
    #  E.params.recThrs = ...;      # set parameters as desired
    #  E.evaluate();                # run per image evaluation
    #  E.accumulate();              # accumulate per image results
    #  E.summarize();               # display summary metrics of results
    # For example usage see evalDemo.m and http://mscoco.org/.
    #
    # The evaluation parameters are as follows (defaults in brackets):
    #  imgIds     - [all] N img ids to use for evaluation
    #  catIds     - [all] K cat ids to use for evaluation
    #  iouThrs    - [.5:.05:.95] T=10 IoU thresholds for evaluation
    #  recThrs    - [0:.01:1] R=101 recall thresholds for evaluation
    #  areaRng    - [...] A=4 object area ranges for evaluation
    #  maxDets    - [1 10 100] M=3 thresholds on max detections per image
    #  iouType    - ['segm'] set iouType to 'segm', 'bbox' or 'keypoints'
    #  iouType replaced the now DEPRECATED useSegm parameter.
    #  useCats    - [1] if true use category labels for evaluation
    # Note: if useCats=0 category labels are ignored as in proposal scoring.
    # Note: multiple areaRngs [Ax2] and maxDets [Mx1] can be specified.
    #
    # evaluate(): evaluates detections on every image and every category and
    # concats the results into the "evalImgs" with fields:
    #  dtIds      - [1xD] id for each of the D detections (dt)
    #  gtIds      - [1xG] id for each of the G ground truths (gt)
    #  dtMatches  - [TxD] matching gt id at each IoU or 0
    #  gtMatches  - [TxG] matching dt id at each IoU or 0
    #  dtScores   - [1xD] confidence of each dt
    #  gtIgnore   - [1xG] ignore flag for each gt
    #  dtIgnore   - [TxD] ignore flag for each dt at each IoU
    #
    # accumulate(): accumulates the per-image, per-category evaluation
    # results in "evalImgs" into the dictionary "eval" with fields:
    #  params     - parameters used for evaluation
    #  date       - date evaluation was performed
    #  counts     - [T,R,K,A,M] parameter dimensions (see above)
    #  precision  - [TxRxKxAxM] precision for every evaluation setting
    #  recall     - [TxKxAxM] max recall for every evaluation setting
    # Note: precision and recall==-1 for settings with no gt objects.
    #
    # See also coco, mask, pycocoDemo, pycocoEvalDemo
    #
    # Microsoft COCO Toolbox.      version 2.0
    # Data, paper, and tutorials available at:  http://mscoco.org/
    # Code written by Piotr Dollar and Tsung-Yi Lin, 2015.
    # Licensed under the Simplified BSD License [see coco/license.txt]
    def __init__(self, cocoGt=None, cocoDt=None, iouType='segm'):
        '''
        Initialize CocoEval using coco APIs for gt and dt
        :param cocoGt: coco object with ground truth annotations
        :param cocoDt: coco object with detection results
        :return: None
        '''
        if not iouType:
            print('iouType not specified. use default iouType segm')
        self.cocoGt   = cocoGt              # ground truth COCO API
        self.cocoDt   = cocoDt              # detections COCO API
        self.params   = {}                  # evaluation parameters
        self.evalImgs = defaultdict(list)   # per-image per-category evaluation results [KxAxI] elements
        self.eval     = {}                  # accumulated evaluation results
        self._gts = defaultdict(list)       # gt for evaluation
        self._dts = defaultdict(list)       # dt for evaluation
        print('iouType', iouType)
        self.params = Params(iouType=iouType) # parameters
        self._paramsEval = {}               # parameters for evaluation
        self.stats = []                     # result summarization
        self.ious = {}                      # ious between all gts and dts
        if not cocoGt is None:
            self.params.imgIds = sorted(cocoGt.getImgIds())
            self.params.catIds = sorted(cocoGt.getCatIds())

    def _prepare(self):
        '''
        Prepare ._gts and ._dts for evaluation based on params
        :return: None
        '''
        def _toMask(anns, coco):
            # modify ann['segmentation'] by reference
            for ann in anns:
                rle = coco.annToRLE(ann)
                ann['segmentation'] = rle
        p = self.params
        if p.useCats:
            gts=self.cocoGt.loadAnns(self.cocoGt.getAnnIds(imgIds=p.imgIds, catIds=p.catIds))
            dts=self.cocoDt.loadAnns(self.cocoDt.getAnnIds(imgIds=p.imgIds, catIds=p.catIds))
        else:
            gts=self.cocoGt.loadAnns(self.cocoGt.getAnnIds(imgIds=p.imgIds))
            dts=self.cocoDt.loadAnns(self.cocoDt.getAnnIds(imgIds=p.imgIds))

        # convert ground truth to mask if iouType == 'segm'
        if p.iouType == 'segm':
            _toMask(gts, self.cocoGt)
            _toMask(dts, self.cocoDt)
        # set ignore flag
        for gt in gts:
            gt['ignore'] = gt['ignore'] if 'ignore' in gt else 0
            gt['ignore'] = 'iscrowd' in gt and gt['iscrowd']
            if p.iouType == 'keypoints':
                gt['ignore'] = (gt['num_keypoints'] == 0) or gt['ignore']
        self._gts = defaultdict(list)       # gt for evaluation
        self._dts = defaultdict(list)       # dt for evaluation
        for gt in gts:
            self._gts[gt['image_id'], gt['category_id']].append(gt)
        for dt in dts:
            self._dts[dt['image_id'], dt['category_id']].append(dt)
        self.evalImgs = defaultdict(list)   # per-image per-category evaluation results
        self.eval     = {}                  # accumulated evaluation results

        #print('before prepare phase')

        pose3d_gt = list(map(lambda x:x['pose_3d'], gts))
        pose3d_dt = list(map(lambda x:x['pred_3d_pts'], dts))

        # print('cocoeval pose3d_gt shape', torch.Tensor(pose3d_gt).shape)
        # print('cocoeval pose3d_gt sample', torch.Tensor(pose3d_gt)[0])

        # print('cocoeval pose3d_dt shape', torch.Tensor(pose3d_dt).shape)
        # print('cocoeval pose3d_dt sample', torch.Tensor(pose3d_dt)[0])

        self.gt_cnt = len(pose3d_gt)

    def evaluate(self):
        '''
        Run per image evaluation on given images and store results (a list of dict) in self.evalImgs
        :return: None
        '''
        tic = time.time()
        print('Running per image evaluation...')
        p = self.params
        # add backward compatibility if useSegm is specified in params
        if not p.useSegm is None:
            p.iouType = 'segm' if p.useSegm == 1 else 'bbox'
            print('useSegm (deprecated) is not None. Running {} evaluation'.format(p.iouType))
        print('Evaluate annotation type *{}*'.format(p.iouType))
        p.imgIds = list(np.unique(p.imgIds))
        if p.useCats:
            p.catIds = list(np.unique(p.catIds))
        p.maxDets = sorted(p.maxDets)
        self.params=p

        self._prepare()
        # loop through images, area range, max detection number
        catIds = p.catIds if p.useCats else [-1]

        if p.iouType == 'segm' or p.iouType == 'bbox':
            computeIoU = self.computeIoU
        elif p.iouType == 'keypoints':
            computeIoU = self.computeOks
        self.ious = {(imgId, catId): computeIoU(imgId, catId) \
                        for imgId in p.imgIds
                        for catId in catIds}

        evaluateImg = self.evaluateImg
        maxDet = p.maxDets[-1]

        global _F_PCK_SCORE1, _F_PCK_SCORE2,_F_PCK_SCORE,_BEST_3D_PRED_POSES, cnt, all_cnt
        global _F_PCK_SCORE1_500, _F_PCK_SCORE1_1k
        global _F_PCK_SCORE2_500, _F_PCK_SCORE2_1k

        _F_PCK_SCORE1, _F_PCK_SCORE2, _F_PCK_SCORE = 0,0, 0
        _F_PCK_SCORE1_500, _F_PCK_SCORE1_1k = 0,0
        _F_PCK_SCORE2_500, _F_PCK_SCORE2_1k = 0,0

        _BEST_3D_PRED_POSES = []
        all_cnt = 0
        cnt = 0

        #print('what are these p.areaRng ? ', p.areaRng)
        self.evalImgs = [evaluateImg(imgId, catId, areaRng, maxDet)
                 for catId in catIds
                 for areaRng in p.areaRng
                 for imgId in p.imgIds
             ]


        # print('-------------  Outside evaluateImg function (variables resetted)  ---------------')

        # print('len evaluated images: ', len(self.evalImgs ))
        # print('_F_PCK_SCORE1: ', _F_PCK_SCORE1)
        # print('_F_PCK_SCORE2: ', _F_PCK_SCORE2)
        # print('_F_PCK_SCORE: ', _F_PCK_SCORE)
        # #print('len(_BEST_3D_PRED_POSES): ', len(_BEST_3D_PRED_POSES))
        # print('cnt: ', cnt)
        # print('all_cnt: ', all_cnt)
        # print('Joe proposed Score 1: ', _F_PCK_SCORE1/cnt)
        # print('Joe proposed Score 2: ', _F_PCK_SCORE2/cnt)
        # print('Joe proposed max Score: ', _F_PCK_SCORE/cnt)

        
        # print('len p.imgIds: ', len(p.imgIds))
        # print('len p.areaRng: ', len(p.areaRng))
        # print('len catIds: ', len(catIds))
        # print('----------------------------------------------------------------------------------')

        

        self._paramsEval = copy.deepcopy(self.params)
        toc = time.time()
        print('DONE (t={:0.2f}s).'.format(toc-tic))


    def computeIoU(self, imgId, catId):
        p = self.params
        if p.useCats:
            gt = self._gts[imgId,catId]
            dt = self._dts[imgId,catId]
        else:
            gt = [_ for cId in p.catIds for _ in self._gts[imgId,cId]]
            dt = [_ for cId in p.catIds for _ in self._dts[imgId,cId]]
        if len(gt) == 0 and len(dt) ==0:
            return []
        inds = np.argsort([-d['score'] for d in dt], kind='mergesort')
        dt = [dt[i] for i in inds]
        if len(dt) > p.maxDets[-1]:
            dt=dt[0:p.maxDets[-1]]

        if p.iouType == 'segm':
            g = [g['segmentation'] for g in gt]
            d = [d['segmentation'] for d in dt]
        elif p.iouType == 'bbox':
            g = [g['bbox'] for g in gt]
            d = [d['bbox'] for d in dt]
        else:
            raise Exception('unknown iouType for iou computation')

        # compute iou between each dt and gt region
        iscrowd = [int(o['iscrowd']) for o in gt]
        ious = maskUtils.iou(d,g,iscrowd)
        return ious

    def computeOks(self, imgId, catId):
        p = self.params
        # dimention here should be Nxm
        gts = self._gts[imgId, catId]
        dts = self._dts[imgId, catId]
        inds = np.argsort([-d['score'] for d in dts], kind='mergesort')
        dts = [dts[i] for i in inds]
        if len(dts) > p.maxDets[-1]:
            dts = dts[0:p.maxDets[-1]]
        # if len(gts) == 0 and len(dts) == 0:
        if len(gts) == 0 or len(dts) == 0:
            return []
        ious = np.zeros((len(dts), len(gts)))
        #sigmas = np.array([.26, .25, .25, .35, .35, .79, .79, .72, .72, .62,.62, 1.07, 1.07, .87, .87, .89, .89])/10.0
        #coco sigmas for hips, knees, & ankles
        sigmas = p.kpt_oks_sigmas

        vars = (sigmas * 2)**2
        k = len(sigmas)
        # compute oks between each detection and ground truth object
        for j, gt in enumerate(gts):
            # create bounds for ignore regions(double the gt bbox)
            g = np.array(gt['keypoints'])
            xg = g[0::3]; yg = g[1::3]; vg = g[2::3]
            k1 = np.count_nonzero(vg > 0)
            bb = gt['bbox']
            x0 = bb[0] - bb[2]; x1 = bb[0] + bb[2] * 2
            y0 = bb[1] - bb[3]; y1 = bb[1] + bb[3] * 2
            for i, dt in enumerate(dts):
                d = np.array(dt['keypoints'])
                xd = d[0::3]; yd = d[1::3]
                if k1>0:
                    # measure the per-keypoint distance if keypoints visible
                    dx = xd - xg
                    dy = yd - yg
                else:
                    # measure minimum distance to keypoints in (x0,y0) & (x1,y1)
                    z = np.zeros((k))
                    dx = np.max((z, x0-xd),axis=0)+np.max((z, xd-x1),axis=0)
                    dy = np.max((z, y0-yd),axis=0)+np.max((z, yd-y1),axis=0)
                #print("dx",dx, 'dy',dy," gt['area']", gt['area'], 'vars', vars)
                e = (dx**2 + dy**2) / vars / (gt['area']+np.spacing(1)) / 2
                if k1 > 0:
                    e=e[vg > 0]
                ious[i, j] = np.sum(np.exp(-e)) / e.shape[0]
        #print(ious)
        return ious

    def pck(self, target, pred, threshold = 100):
        '''
        Percentage of Correct Keypoint for 3D pose Evaluation where PCKh @ 0.1m (10cm/100mm)

        Arguments:
        target: A tensor of shape (1, 18) : global values relative to hip in our case
        pred: A tensor of shape (1, 18) : global values relative to hip in our case

        Returns:
            pck_score: A scalar value btw 0 and 1
        '''
        diff = torch.abs(target - pred)
        count = torch.sum(diff < threshold, dtype=torch.float)
        pck_score = count/ (target.shape[0]*target.shape[1])
        return pck_score

    def mpjpe_error(self, inps, out):
        '''
        MPJPE ERROR

        Arguments:
        target: A tensor of shape (3, 6) : global values relative to hip in our case
        pred: A tensor of shape (3, 6) : global values relative to hip in our case

        Returns:
            mpjpe_erro: A scalar value
        '''
        error = sum(((out-inps)**2).sum(dim=0).sqrt())/inps.shape[1]
        return error

    def evaluateImg(self, imgId, catId, aRng, maxDet):
        '''
        perform evaluation for single category and image
        :return: dict (single image results)
        '''
        p = self.params
        catIds = p.catIds if p.useCats else [-1]
        # print('len p.imgIds: ', len(p.imgIds))
        # print('len p.areaRng: ', len(p.areaRng))
        # print('len catIds: ', len(catIds))

        # print(f'imgId:{imgId}, catId:{catId}, aRng:{aRng}, maxDet:{maxDet}')
        if p.useCats:
            gt = self._gts[imgId,catId]
            dt = self._dts[imgId,catId]
        else:
            gt = [_ for cId in p.catIds for _ in self._gts[imgId,cId]]
            dt = [_ for cId in p.catIds for _ in self._dts[imgId,cId]]
        if len(gt) == 0 and len(dt) ==0:
            return None

        for g in gt:
            if g['ignore'] or (g['area']<aRng[0] or g['area']>aRng[1]):
                g['_ignore'] = 1
            else:
                g['_ignore'] = 0

        # sort dt highest score first, sort gt ignore last
        gtind = np.argsort([g['_ignore'] for g in gt], kind='mergesort')
        gt = [gt[i] for i in gtind]
        dtind = np.argsort([-d['score'] for d in dt], kind='mergesort')

        #print('dtind length, some example 2d scores', len(dtind), dtind[0:10])
        dt = [dt[i] for i in dtind[0:maxDet]]
        #print('checking dt', dt[0:10])

        iscrowd = [int(o['iscrowd']) for o in gt]
        # load computed ious
        ious = self.ious[imgId, catId][:, gtind] if len(self.ious[imgId, catId]) > 0 else self.ious[imgId, catId]

        T = len(p.iouThrs)
        G = len(gt)
        D = len(dt)
        gtm  = np.zeros((T,G))
        dtm  = np.zeros((T,D))
        gtIg = np.array([g['_ignore'] for g in gt])
        dtIg = np.zeros((T,D))

        #print('len of dt and gt before for loops', len(dt), len(gt))
        if not len(ious)==0:
            for tind, t in enumerate(p.iouThrs):
                #print('tind, t', tind, t)
                for dind, d in enumerate(dt):
                    # information about best match so far (m=-1 -> unmatched)
                    iou = min([t,1-1e-10])
                    #print('iou', iou)
                    m   = -1
                    for gind, g in enumerate(gt):
                        # if this gt already matched, and not a crowd, continue
                        if gtm[tind,gind]>0 and not iscrowd[gind]:
                            continue
                        # if dt matched to reg gt, and on ignore gt, stop
                        if m>-1 and gtIg[m]==0 and gtIg[gind]==1:
                            break
                        # continue to next gt unless better match made
                        if ious[dind,gind] < iou:
                            continue
                        # if match successful and best so far, store appropriately
                        iou=ious[dind,gind]
                        m=gind
                    # if match made store id of match for both dt and gt
                    if m ==-1:
                        continue
                    dtIg[tind,dind] = gtIg[m]
                    dtm[tind,dind]  = gt[m]['id']
                    gtm[tind,m]     = d['id']
        # set unmatched detections outside of area range to ignore
        a = np.array([d['area']<aRng[0] or d['area']>aRng[1] for d in dt]).reshape((1, len(dt)))
        dtIg = np.logical_or(dtIg, np.logical_and(dtm==0, np.repeat(a,T,0)))


        ############ 3D Evaluation ###############################
        #print('performing 3D Evaluation')
        GT  = torch.Tensor(list(map(lambda x:x['pose_3d'], gt)))
        DT  = torch.Tensor(list(map(lambda x:x['pred_3d_pts'], dt)))
        #print('GT 3d shape', GT.shape)
        #print('DT 3d shape', DT.shape)

        if torch.sum(torch.isnan(GT)):
            return {
                'image_id':     imgId,
                'category_id':  catId,
                'aRng':         aRng,
                'maxDet':       maxDet,
                'dtIds':        [d['id'] for d in dt],
                'gtIds':        [g['id'] for g in gt],
                'dtMatches':    dtm,
                'gtMatches':    gtm,
                'dtScores':     [d['score'] for d in dt],
                'gtIgnore':     gtIg,
                'dtIgnore':     dtIg,
            }

        #print(gt[0])
        #print(dt[0])

        GT_2d  = torch.Tensor(list(map(lambda x:x['keypoints'], gt))) #(x,y, visibility)
        DT_2d  = torch.Tensor(list(map(lambda x:x['keypoints'], dt))) #(x,y,score)  
        
        # print('GT_2d', GT_2d)
        # print()
        # print()
        # print('DT_2d', DT_2d)    

        #print('GT 2d shape', GT_2d.shape)
        #print('DT 2d shape', DT_2d.shape)


        #Normalize relative to the hip
        #print('GT shape', GT.shape)
        GT = GT.view(GT.shape[0], 6,3) #1,6,3
        midhip = (GT[:,0] + GT[:,1])/2

        #print('GT shape, midhip shape', GT.shape, midhip.unsqueeze(1).shape)
        GT = GT - midhip.unsqueeze(1)
        #GT = GT.view(GT.shape[0], -1)

        GT = GT.view(GT.shape[0], -1) #1,18

        #Normalize 3d GT by mean-std relative to the hip
        mean_3d, std_3d = (torch.Tensor([   90.4226,   -99.0404,   113.7033,   -90.4226,    99.0404,  -113.7033,
            -1257.6155, -1297.9100, -1227.4360, -1220.5818, -1329.1154, -1301.5215,
              797.3640,   756.3050,   403.3004,   410.9879,   -14.6912,    16.2920]),
        torch.Tensor([ 15.5230,  19.4742,  25.6194,  15.5230,  19.4742,  25.6194, 183.8460,
            172.6190, 212.3050, 218.0117, 192.0247, 208.0867, 178.1015, 186.4496,
            160.7282, 160.8192, 163.5823, 152.6740]))

        
        #print('Global 3d GT sample in Evaluation: ', GT[0:5])

        # print('last gt sample', GT[0])
        # print('last dt sample', DT[0])
        # print()
        # print('last gt shape', GT.shape)
        # print('last dt shape', DT.shape)


        best_score_3d = float('-inf')
        best_score_2d = float('-inf')
        least_error_3d = float('inf')
        #all_nan = torch.isnan(GT)

        global _F_PCK_SCORE1, _F_PCK_SCORE2, _F_PCK_SCORE, _BEST_3D_PRED_POSES, cnt, all_cnt
        global _F_PCK_SCORE1_500, _F_PCK_SCORE1_1k
        global _F_PCK_SCORE2_500, _F_PCK_SCORE2_1k

        DT = torch.Tensor(DT)

        #mean detection
        mean_dt = DT.mean(dim=0) 
        mean_dt = torch.Tensor(mean_dt).view(1,-1)
        mean_dt = (mean_dt * std_3d) + mean_3d #return to global dt for evaluation 
        #print('sample mean', mean_dt[0][0:5])

        score_3d_mean = self.pck(GT, mean_dt, 100)
        loss_mean = torch.nn.functional.mse_loss(GT, mean_dt)
        target = GT.view(3,6); pred = mean_dt.view(3,6)
        error_3d_mean = self.mpjpe_error(target, pred)

        #median detection
        med_dt = DT.median(dim=0)[0] 
        med_dt = torch.Tensor(med_dt).view(1,-1)
        med_dt = (med_dt * std_3d) + mean_3d #return to global dt for evaluation 
        #print('sample median', med_dt[0][0:5])

        #plot 3d median dt and GT
        # fig=plt.figure(figsize=(20, 5), dpi= 80, facecolor='w', edgecolor='k')
        # axes=fig.subplots(1,6)

        # axs=[]
        # f = plt.figure(figsize=(10,10))
        # axs.append(f.add_subplot(2,3,1, projection='3d'))
        # axs.append(f.add_subplot(2,3,2, projection='3d'))
        # axs.append(f.add_subplot(2,3,3, projection='3d'))

        

        # print('*******before PCK***')
        # print('GT', GT)
        # print('med_dt', med_dt)

        score_3d_med = self.pck(GT, med_dt, 100)
        # print('score_3d_med', score_3d_med)
        # print()
        # print()

        loss_med = torch.nn.functional.mse_loss(GT, med_dt)
        target = GT.view(3,6); pred = med_dt.view(3,6)
        error_3d_med = self.mpjpe_error(target, pred)

        # print('mean 3d error in {} instances'.format(len(DT)), error_3d_mean)
        # print('correspodning 3d PCK score in {} instances'.format(len(DT)), score_3d_mean)
        # print('loss mean: ', loss_mean)

        # print('median 3d error in {} instances'.format(len(DT)), error_3d_med)
        # print('correspodning 3d PCK score in {} instances'.format(len(DT)), score_3d_med)
        # print('loss median: ', loss_med)

        _F_PCK_SCORE1 += score_3d_mean
        # print('_F_PCK_SCORE1', _F_PCK_SCORE1)
        # print()
        _F_PCK_SCORE2 += score_3d_med
        # print('_F_PCK_SCORE2', _F_PCK_SCORE2)

        _F_PCK_SCORE1_500 += self.pck(GT, mean_dt, 250) #mean is 1
        _F_PCK_SCORE1_1k += self.pck(GT, mean_dt, 500)

        _F_PCK_SCORE2_500 += self.pck(GT, med_dt, 250)
        _F_PCK_SCORE2_1k += self.pck(GT, med_dt, 500)
        #_BEST_3D_PRED_POSES.append(best_3d)
        #cnt+=1

        for i, (dt_, dt_2d) in enumerate(zip(DT, DT_2d)):
        #for i, dt_ in enumerate(DT):
            dt_ = (dt_ * std_3d) + mean_3d #return to global dt for evaluation 
            dt_g = torch.Tensor(dt_).view(1,-1)

            #consider only valid
            #print('GT type, dt type, gt shape, dt_ shape', type(GT), type(dt_g), GT.shape, dt_g.shape)

            score_3d = self.pck(GT, dt_g)
            score_2d = self.pck(GT_2d, dt_2d)
            #loss = torch.nn.functional.mse_loss(dt_g[~all_nan], GT[~all_nan])
            loss = torch.nn.functional.mse_loss(dt_, GT)
            loss_2 = torch.nn.functional.mse_loss(GT_2d, dt_2d)

            target = GT.view(3,6); pred = dt_.view(3,6)
            error_3d = self.mpjpe_error(target, pred)

            target = GT_2d.view(3,6); pred = dt_2d.view(3,6)
            error_2d = self.mpjpe_error(target, pred)

            # print(i, 'pck score on 2d', score_2d)
            # print(i, 'pck score on 3d', score_3d)
            # print(i, 'mse loss 3d', loss)
            # print(i, 'mse loss 2d', loss_2)
            # print(i, 'mpjpe 3d error', error_3d)
            # print(i, 'mpjpe 2d error', error_2d)

            all_cnt+=1

            #corresponding 3D detected using best 2D
            # if score_2d > best_score_2d:
            #     print('yes')
            #     best_score_2d = score_2d
            #     best_pred_2d = dt_2d
            #     best_index = i
            #     best_score_3d = score_3d
            #     best_3d = dt_g
            #     report_error_3d = error_3d
            #     report_error_2d = error_2d
            #     best_loss = loss
            #     best_loss_2 = loss_2

            #3D best
            if error_3d < least_error_3d:
                least_error_3d = error_3d
                best_index = i
                best_score_3d = score_3d
                best_3d = dt_g

                #report_error_3d = error_3d
                report_error_2d = error_2d
                
                best_loss = loss
                best_loss_2 = loss_2

            

            # if score > best_score:
            #     best_score = score
            #     best_pred = dt_g

        #print('max least 3d error in {} instances'.format(len(DT)), least_error_3d)
        #print('max 3d PCK score in {} instances'.format(len(DT)), best_score_3d)
        #print('max 2d mpjpe error in {} instances'.format(len(DT)), report_error_2d)
        #print('correspodning 3d mpjpe error in {} instances'.format(len(DT)), report_error_3d)
        #print('max loss 3d: ', best_loss)
        #print('max loss 2d : ', best_loss_2)

        _F_PCK_SCORE += best_score_3d
        #_BEST_3D_PRED_POSES.append(best_3d)
        cnt+=1

        #print(f'cnt:{cnt} all_cnt:{all_cnt}')

        #print('3D pck score for this image: {}', report_error_3d)


        # store results for given image and category
        return {
                'image_id':     imgId,
                'category_id':  catId,
                'aRng':         aRng,
                'maxDet':       maxDet,
                'dtIds':        [d['id'] for d in dt],
                'gtIds':        [g['id'] for g in gt],
                'dtMatches':    dtm,
                'gtMatches':    gtm,
                'dtScores':     [d['score'] for d in dt],
                'gtIgnore':     gtIg,
                'dtIgnore':     dtIg,
            }

    def accumulate(self, p = None):
        '''
        Accumulate per image evaluation results and store the result in self.eval
        :param p: input params for evaluation
        :return: None
        '''
        print('Accumulating evaluation results...')
        tic = time.time()
        if not self.evalImgs:
            print('Please run evaluate() first')
        # allows input customized parameters
        if p is None:
            p = self.params
        p.catIds = p.catIds if p.useCats == 1 else [-1]
        T           = len(p.iouThrs)
        R           = len(p.recThrs)
        K           = len(p.catIds) if p.useCats else 1
        A           = len(p.areaRng)
        M           = len(p.maxDets)

        #print('T, R, K,A, M', T, R, K,A, M)

        precision   = -np.ones((T,R,K,A,M)) # -1 for the precision of absent categories
        recall      = -np.ones((T,K,A,M))
        scores      = -np.ones((T,R,K,A,M))

        # create dictionary for future indexing
        _pe = self._paramsEval
        catIds = _pe.catIds if _pe.useCats else [-1]
        setK = set(catIds)
        setA = set(map(tuple, _pe.areaRng))
        setM = set(_pe.maxDets)
        setI = set(_pe.imgIds)
        # get inds to evaluate
        k_list = [n for n, k in enumerate(p.catIds)  if k in setK]
        m_list = [m for n, m in enumerate(p.maxDets) if m in setM]
        a_list = [n for n, a in enumerate(map(lambda x: tuple(x), p.areaRng)) if a in setA]
        i_list = [n for n, i in enumerate(p.imgIds)  if i in setI]
        I0 = len(_pe.imgIds)
        A0 = len(_pe.areaRng)
        # retrieve E at each category, area range, and max number of detections
        for k, k0 in enumerate(k_list):
            Nk = k0*A0*I0
            for a, a0 in enumerate(a_list):
                Na = a0*I0
                for m, maxDet in enumerate(m_list):
                    E = [self.evalImgs[Nk + Na + i] for i in i_list]
                    E = [e for e in E if not e is None]
                    if len(E) == 0:
                        continue
                    dtScores = np.concatenate([e['dtScores'][0:maxDet] for e in E])

                    # different sorting method generates slightly different results.
                    # mergesort is used to be consistent as Matlab implementation.
                    inds = np.argsort(-dtScores, kind='mergesort')
                    dtScoresSorted = dtScores[inds]

                    dtm  = np.concatenate([e['dtMatches'][:,0:maxDet] for e in E], axis=1)[:,inds]
                    dtIg = np.concatenate([e['dtIgnore'][:,0:maxDet]  for e in E], axis=1)[:,inds]
                    gtIg = np.concatenate([e['gtIgnore'] for e in E])
                    npig = np.count_nonzero(gtIg==0 )
                    if npig == 0:
                        continue
                    tps = np.logical_and(               dtm,  np.logical_not(dtIg) )
                    fps = np.logical_and(np.logical_not(dtm), np.logical_not(dtIg) )

                    tp_sum = np.cumsum(tps, axis=1).astype(dtype=np.float)
                    fp_sum = np.cumsum(fps, axis=1).astype(dtype=np.float)
                    for t, (tp, fp) in enumerate(zip(tp_sum, fp_sum)):
                        tp = np.array(tp)
                        fp = np.array(fp)
                        nd = len(tp)
                        rc = tp / npig
                        pr = tp / (fp+tp+np.spacing(1))
                        q  = np.zeros((R,))
                        ss = np.zeros((R,))

                        if nd:
                            recall[t,k,a,m] = rc[-1]
                        else:
                            recall[t,k,a,m] = 0

                        # numpy is slow without cython optimization for accessing elements
                        # use python array gets significant speed improvement
                        pr = pr.tolist(); q = q.tolist()

                        for i in range(nd-1, 0, -1):
                            if pr[i] > pr[i-1]:
                                pr[i-1] = pr[i]

                        inds = np.searchsorted(rc, p.recThrs, side='left')
                        try:
                            for ri, pi in enumerate(inds):
                                q[ri] = pr[pi]
                                ss[ri] = dtScoresSorted[pi]
                        except:
                            pass
                        precision[t,:,k,a,m] = np.array(q)
                        scores[t,:,k,a,m] = np.array(ss)
        self.eval = {
            'params': p,
            'counts': [T, R, K, A, M],
            'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'precision': precision,
            'recall':   recall,
            'scores': scores,
        }
        toc = time.time()
        print('DONE (t={:0.2f}s).'.format( toc-tic))


    def summarize(self):
        '''
        Compute and display summary metrics for evaluation results.
        Note this functin can *only* be applied on the default parameter setting
        '''
        

        #3D Evaluation Final Score
        global _F_PCK_SCORE1, _F_PCK_SCORE2,_F_PCK_SCORE, _BEST_3D_PRED_POSES, cnt, all_cnt
        global _F_PCK_SCORE1_500, _F_PCK_SCORE1_1k
        global _F_PCK_SCORE2_500, _F_PCK_SCORE2_1k
        
        if cnt > 10:
            display.clear_output(wait=True)

        print('_F_PCK_SCORE1 @100', _F_PCK_SCORE1)
        print('_F_PCK_SCORE2 @100', _F_PCK_SCORE2)
        print('_F_PCK_SCORE greedy @100', _F_PCK_SCORE)

        print('_F_PCK_SCORE1 @ 250', _F_PCK_SCORE1_500)
        print('_F_PCK_SCORE1 @ 250', _F_PCK_SCORE2_500)

        print('_F_PCK_SCORE1 @ 500', _F_PCK_SCORE1_1k)
        print('_F_PCK_SCORE1 @ 500', _F_PCK_SCORE2_1k)
        
        print('cnt', cnt)
        print('all_cnt', all_cnt)

        print('final score (mean) @100', _F_PCK_SCORE1/cnt)
        print('final score (median) @100', _F_PCK_SCORE2/cnt)
        print('final score (greedy)', _F_PCK_SCORE/cnt)

        print('final score (mean) @ 250', _F_PCK_SCORE1_500/cnt)
        print('final score (median) @ 250', _F_PCK_SCORE2_500/cnt)

        print('final score (mean) @ 500', _F_PCK_SCORE1_1k/cnt)
        print('final score (median) @ 500', _F_PCK_SCORE2_1k/cnt)

        f = open("/content/output.txt", "a")

        try:
            time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"timestamp: {time}", file=f)
        except:
            pass
        print(f"_F_PCK_SCORE1 @100 ={_F_PCK_SCORE1}", file=f)
        print(f"_F_PCK_SCORE2 @100' ={_F_PCK_SCORE2}", file=f)
        print(f"_F_PCK_SCORE @100' = {_F_PCK_SCORE}", file=f)
        
        print(f"cnt =  {cnt}", file=f)
        print(f"all_cnt =  {all_cnt}", file=f)

        print(f"final score (mean) @100 = {_F_PCK_SCORE1/cnt}", file=f)
        print(f"final score (median) @100' = {_F_PCK_SCORE2/cnt}", file=f)
        print(f"final score (greedy) = {_F_PCK_SCORE/cnt}", file=f)

        print(f"final score (mean) @ 250' = {_F_PCK_SCORE1_500/cnt}", file=f)
        print(f"final score (median) @ 250' =  {_F_PCK_SCORE2_500/cnt}", file=f)

        print(f"final score (mean) @ 500' = {_F_PCK_SCORE1_1k/cnt}", file=f)
        print(f"final score (median) @ 500' = {_F_PCK_SCORE2_1k/cnt}", file=f)
        print(f"   ", file=f)
        

        #print(f"WER = {sum(wer_nums)/sum(wer_denoms)}", file=f)
        f.close()

        #print('**********3D Final PCK score on {} images: {}************'.format(self.gt_cnt, _F_PCK_SCORE/self.gt_cnt))
        #print('First 5 ', _BEST_3D_PRED_POSES[0:5])

        def _summarize( ap=1, iouThr=None, areaRng='all', maxDets=100 ):
            p = self.params
            iStr = ' {:<18} {} @[ IoU={:<9} | area={:>6s} | maxDets={:>3d} ] = {:0.3f}'
            titleStr = 'Average Precision' if ap == 1 else 'Average Recall'
            typeStr = '(AP)' if ap==1 else '(AR)'
            iouStr = '{:0.2f}:{:0.2f}'.format(p.iouThrs[0], p.iouThrs[-1]) \
                if iouThr is None else '{:0.2f}'.format(iouThr)

            aind = [i for i, aRng in enumerate(p.areaRngLbl) if aRng == areaRng]
            mind = [i for i, mDet in enumerate(p.maxDets) if mDet == maxDets]
            if ap == 1:
                # dimension of precision: [TxRxKxAxM]
                s = self.eval['precision']
                # IoU
                if iouThr is not None:
                    t = np.where(iouThr == p.iouThrs)[0]
                    s = s[t]
                s = s[:,:,:,aind,mind]
            else:
                # dimension of recall: [TxKxAxM]
                s = self.eval['recall']
                if iouThr is not None:
                    t = np.where(iouThr == p.iouThrs)[0]
                    s = s[t]
                s = s[:,:,aind,mind]
            if len(s[s>-1])==0:
                mean_s = -1
            else:
                mean_s = np.mean(s[s>-1])
            print(iStr.format(titleStr, typeStr, iouStr, areaRng, maxDets, mean_s))
            return mean_s
        def _summarizeDets():
            stats = np.zeros((12,))
            stats[0] = _summarize(1)
            stats[1] = _summarize(1, iouThr=.5, maxDets=self.params.maxDets[2])
            stats[2] = _summarize(1, iouThr=.75, maxDets=self.params.maxDets[2])
            stats[3] = _summarize(1, areaRng='small', maxDets=self.params.maxDets[2])
            stats[4] = _summarize(1, areaRng='medium', maxDets=self.params.maxDets[2])
            stats[5] = _summarize(1, areaRng='large', maxDets=self.params.maxDets[2])
            stats[6] = _summarize(0, maxDets=self.params.maxDets[0])
            stats[7] = _summarize(0, maxDets=self.params.maxDets[1])
            stats[8] = _summarize(0, maxDets=self.params.maxDets[2])
            stats[9] = _summarize(0, areaRng='small', maxDets=self.params.maxDets[2])
            stats[10] = _summarize(0, areaRng='medium', maxDets=self.params.maxDets[2])
            stats[11] = _summarize(0, areaRng='large', maxDets=self.params.maxDets[2])
            return stats
        def _summarizeKps():
            stats = np.zeros((10,))
            stats[0] = _summarize(1, maxDets=20)
            stats[1] = _summarize(1, maxDets=20, iouThr=.5)
            stats[2] = _summarize(1, maxDets=20, iouThr=.75)
            stats[3] = _summarize(1, maxDets=20, areaRng='medium')
            stats[4] = _summarize(1, maxDets=20, areaRng='large')
            stats[5] = _summarize(0, maxDets=20)
            stats[6] = _summarize(0, maxDets=20, iouThr=.5)
            stats[7] = _summarize(0, maxDets=20, iouThr=.75)
            stats[8] = _summarize(0, maxDets=20, areaRng='medium')
            stats[9] = _summarize(0, maxDets=20, areaRng='large')
            return stats
        if not self.eval:
            raise Exception('Please run accumulate() first')
        iouType = self.params.iouType
        if iouType == 'segm' or iouType == 'bbox':
            summarize = _summarizeDets
        elif iouType == 'keypoints':
            summarize = _summarizeKps
        self.stats = summarize()

    def __str__(self):
        self.summarize()


class Params:
    '''
    Params for coco evaluation api
    '''
    def setDetParams(self):
        self.imgIds = []
        self.catIds = []
        # np.arange causes trouble.  the data point on arange is slightly larger than the true value
        self.iouThrs = np.linspace(.5, 0.95, int((0.95 - .5) / .05) + 1, endpoint=True)
        self.recThrs = np.linspace(.0, 1.00, int((1.00 - .0) / .01) + 1, endpoint=True)
        self.maxDets = [1, 10, 100]
        self.areaRng = [[0 ** 2, 1e5 ** 2], [0 ** 2, 32 ** 2], [32 ** 2, 96 ** 2], [96 ** 2, 1e5 ** 2]]
        self.areaRngLbl = ['all', 'small', 'medium', 'large']
        self.useCats = 1

    def setKpParams(self):
        self.imgIds = []
        self.catIds = []
        # np.arange causes trouble.  the data point on arange is slightly larger than the true value
        self.iouThrs = np.linspace(.5, 0.95, int((0.95 - .5) / .05) + 1, endpoint=True)
        self.recThrs = np.linspace(.0, 1.00, int((1.00 - .0) / .01) + 1, endpoint=True)
        self.maxDets = [20]
        self.areaRng = [[0 ** 2, 1e5 ** 2], [32 ** 2, 96 ** 2], [96 ** 2, 1e5 ** 2]]
        self.areaRngLbl = ['all', 'medium', 'large']
        self.useCats = 1
        self.kpt_oks_sigmas  = np.array([1.07, 1.07, 0.87, 0.87, 0.89, 0.89]) # divide by 10 #np.array([.9,.9,.9,.9,.9,.9])

    def __init__(self, iouType='segm'):
        if iouType == 'segm' or iouType == 'bbox':
            self.setDetParams()
        elif iouType == 'keypoints':
            self.setKpParams()
        else:
            raise Exception('iouType not supported')
        self.iouType = iouType
        # useSegm is deprecated
        self.useSegm = None
