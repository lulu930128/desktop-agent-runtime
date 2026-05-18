/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

import { CubismDefaultParameterId } from '@framework/cubismdefaultparameterid';
import { CubismModelSettingJson } from '@framework/cubismmodelsettingjson';
import {
  BreathParameterData,
  CubismBreath
} from '@framework/effect/cubismbreath';
import { LookParameterData, CubismLook } from '@framework/effect/cubismlook';
import { CubismEyeBlink } from '@framework/effect/cubismeyeblink';
import { ICubismModelSetting } from '@framework/icubismmodelsetting';
import { CubismIdHandle } from '@framework/id/cubismid';
import { CubismFramework } from '@framework/live2dcubismframework';
import { CubismMatrix44 } from '@framework/math/cubismmatrix44';
import { CubismUserModel } from '@framework/model/cubismusermodel';
import {
  ACubismMotion,
  BeganMotionCallback,
  FinishedMotionCallback
} from '@framework/motion/acubismmotion';
import { CubismMotion } from '@framework/motion/cubismmotion';
import {
  CubismMotionQueueEntryHandle,
  InvalidMotionQueueEntryHandleValue
} from '@framework/motion/cubismmotionqueuemanager';
import { CubismUpdateScheduler } from '@framework/motion/cubismupdatescheduler';
import { CubismBreathUpdater } from '@framework/motion/cubismbreathupdater';
import { CubismLookUpdater } from '@framework/motion/cubismlookupdater';
import { CubismEyeBlinkUpdater } from '@framework/motion/cubismeyeblinkupdater';
import { CubismExpressionUpdater } from '@framework/motion/cubismexpressionupdater';
import { CubismPhysicsUpdater } from '@framework/motion/cubismphysicsupdater';
import { CubismPoseUpdater } from '@framework/motion/cubismposeupdater';
import { CubismLipSyncUpdater } from '@framework/motion/cubismlipsyncupdater';
import { csmRect } from '@framework/type/csmrectf';
import {
  CSM_ASSERT,
  CubismLogError,
  CubismLogInfo
} from '@framework/utils/cubismdebug';

import * as LAppDefine from './lappdefine';
import { LAppPal } from './lapppal';
import { TextureInfo } from './lapptexturemanager';
import { LAppWavFileHandler } from './lappwavfilehandler';
import { CubismMoc } from '@framework/model/cubismmoc';
import { CubismShaderManager_WebGL } from '@framework/rendering/cubismshader_webgl';
import { LAppSubdelegate } from './lappsubdelegate';

function isAbsoluteAssetUrl(value: string): boolean {
  return /^(https?:|file:|blob:|data:)/i.test(String(value || '').trim());
}

function resolveAssetUrl(baseUrl: string, value: string): string {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return normalized;
  }
  if (isAbsoluteAssetUrl(normalized)) {
    return normalized;
  }
  return new URL(normalized, baseUrl).toString();
}

function withCacheBust(assetUrl: string, cacheBust: string): string {
  if (!assetUrl || /^(data:|blob:)/i.test(assetUrl)) {
    return assetUrl;
  }

  try {
    const url = new URL(assetUrl, window.location.href);
    url.searchParams.set('kuroLive2dBust', cacheBust);
    return url.toString();
  } catch (_error) {
    const separator = assetUrl.includes('?') ? '&' : '?';
    return `${assetUrl}${separator}kuroLive2dBust=${encodeURIComponent(cacheBust)}`;
  }
}

function absolutizeModelSetting(rawText: string, modelUrl: string): string {
  const payload = JSON.parse(rawText);
  const refs = payload?.FileReferences || {};

  const absolutizeValue = (value: unknown) => {
    if (typeof value === 'string' && value.trim()) {
      return resolveAssetUrl(modelUrl, value);
    }
    return value;
  };

  refs.Moc = absolutizeValue(refs.Moc);
  refs.Physics = absolutizeValue(refs.Physics);
  refs.Pose = absolutizeValue(refs.Pose);
  refs.UserData = absolutizeValue(refs.UserData);
  refs.DisplayInfo = absolutizeValue(refs.DisplayInfo);

  if (Array.isArray(refs.Textures)) {
    refs.Textures = refs.Textures.map((value: unknown) => absolutizeValue(value));
  }

  if (Array.isArray(refs.Expressions)) {
    refs.Expressions = refs.Expressions.map((item: any) =>
      item && typeof item === 'object'
        ? {
            ...item,
            File: absolutizeValue(item.File)
          }
        : item
    );
  }

  if (refs.Motions && typeof refs.Motions === 'object') {
    for (const [groupName, motions] of Object.entries(refs.Motions)) {
      if (!Array.isArray(motions)) {
        continue;
      }
      refs.Motions[groupName] = motions.map((item: any) =>
        item && typeof item === 'object'
          ? {
              ...item,
              File: absolutizeValue(item.File),
              Sound: absolutizeValue(item.Sound)
            }
          : item
      );
    }
  }

  payload.FileReferences = refs;
  return JSON.stringify(payload);
}

function safeModelSettingString(
  setting: ICubismModelSetting,
  getterName: string
): string {
  try {
    const getter = (setting as unknown as Record<string, unknown>)[getterName];
    if (typeof getter !== 'function') {
      return '';
    }
    const value = (getter as () => unknown).call(setting);
    return typeof value === 'string' ? value : '';
  } catch (error) {
    console.warn('[pet-renderer] Optional model setting lookup failed', {
      getterName,
      error: error instanceof Error ? error.message : String(error)
    });
    return '';
  }
}

enum LoadStep {
  LoadAssets,
  LoadModel,
  WaitLoadModel,
  LoadExpression,
  WaitLoadExpression,
  LoadPhysics,
  WaitLoadPhysics,
  LoadPose,
  WaitLoadPose,
  SetupEyeBlink,
  SetupBreath,
  LoadUserData,
  WaitLoadUserData,
  SetupEyeBlinkIds,
  SetupLipSyncIds,
  SetupLook,
  SetupLayout,
  LoadMotion,
  WaitLoadMotion,
  CompleteInitialize,
  CompleteSetupModel,
  LoadTexture,
  WaitLoadTexture,
  CompleteSetup
}

const SKIP_OPTIONAL_PHYSICS = true;
const MINIMAL_RENDERER_BOOT = true;

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

function clampSigned(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(-1, value));
}

function clampExternalParameterValue(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(-1, value));
}

type IdleWaveParameterSpec = {
  parameterId: string;
  amplitude: number;
  speed: number;
  phase: number;
  weightScale: number;
};

type IdleWaveParameter = {
  id: CubismIdHandle;
  amplitude: number;
  speed: number;
  phase: number;
  weightScale: number;
};

type ExternalParameterTarget = {
  id: CubismIdHandle | null;
  parameterIndex: number | null;
  currentValue: number;
  targetValue: number;
  durationSeconds: number;
};

function createIdleWaveSpecs(
  parameterIds: string[],
  amplitude: number,
  speed: number,
  phase: number,
  phaseStep: number,
  weightScale: number
): IdleWaveParameterSpec[] {
  return parameterIds.map((parameterId, index) => ({
    parameterId,
    amplitude: amplitude * (index % 2 === 0 ? 1 : -0.82),
    speed: speed + (index % 3) * 0.035,
    phase: phase + index * phaseStep,
    weightScale
  }));
}

/**
 * ユーザーが実際に使用するモデルの実装クラス<br>
 * モデル生成、機能コンポーネント生成、更新処理とレンダリングの呼び出しを行う。
 */
export class LAppModel extends CubismUserModel {
  private static readonly FallbackMouthParameterIds = ['ParamMouthOpenY'];
  private static readonly FallbackEyeBlinkParameterIds = [
    'ParamEyeLOpen',
    'ParamEyeROpen'
  ];
  private static readonly SecondaryIdleWaveParameterSpecs: IdleWaveParameterSpec[] = [
    ...createIdleWaveSpecs(
      ['Param17', 'Param18', 'Param19', 'Param20', 'Param21', 'Param22', 'Param23', 'Param24', 'Param25', 'Param26'],
      5.2,
      0.68,
      0.15,
      0.47,
      0.56
    ),
    ...createIdleWaveSpecs(
      ['Param27', 'Param28', 'Param29'],
      4.2,
      0.74,
      1.1,
      0.72,
      0.45
    ),
    ...createIdleWaveSpecs(
      ['Param30', 'Param31', 'Param32', 'Param33', 'Param34', 'Param35', 'Param36', 'Param37'],
      7.0,
      0.48,
      0.55,
      0.39,
      0.52
    ),
    ...createIdleWaveSpecs(
      ['Param38', 'Param39', 'Param40', 'Param41', 'Param42', 'Param43', 'Param44', 'Param45', 'Param46', 'Param47', 'Param48', 'Param49'],
      4.8,
      0.38,
      0.2,
      0.31,
      0.42
    ),
    ...createIdleWaveSpecs(
      ['Param50', 'Param51', 'Param52', 'Param53', 'Param54', 'Param55', 'Param56', 'Param57', 'Param58', 'Param59', 'Param60', 'Param61'],
      5.4,
      0.34,
      1.0,
      0.28,
      0.44
    ),
    ...createIdleWaveSpecs(
      ['Param62', 'Param63', 'Param64', 'Param65', 'Param66', 'Param67', 'Param68', 'Param69', 'Param70', 'Param71', 'Param72', 'Param73', 'Param74', 'Param75', 'Param76'],
      6.0,
      0.31,
      1.8,
      0.24,
      0.48
    ),
    ...createIdleWaveSpecs(
      ['Param77', 'Param78', 'Param79', 'Param80'],
      6.5,
      0.42,
      0.7,
      0.58,
      0.5
    ),
    ...createIdleWaveSpecs(
      ['Param81', 'Param82', 'Param83', 'Param84', 'Param85', 'Param86', 'Param87', 'Param88'],
      5.8,
      0.58,
      1.35,
      0.43,
      0.55
    )
  ];
  private _mouthDebugPulseActive: boolean;
  private _mouthDebugPulseElapsed: number;
  private _mouthDebugPulseDuration: number;
  private _externalParameterTargets: Map<string, ExternalParameterTarget>;
  private _assetCacheBust: string;

  private resolveAssetPath(assetPath: string): string {
    return withCacheBust(resolveAssetUrl(this._modelHomeDir, assetPath), this._assetCacheBust);
  }
  /**
   * model3.jsonが置かれたディレクトリとファイルパスからモデルを生成する
   * @param dir
   * @param fileName
   */
  public loadAssets(dir: string, fileName: string): void {
    this._modelHomeDir = dir;
    this._assetCacheBust = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    const modelUrl = this.resolveAssetPath(fileName);

    fetch(modelUrl, { cache: 'no-store' })
      .then(response => {
        console.info('[pet-renderer] model3 fetch response', {
          url: modelUrl,
          status: response.status,
          ok: response.ok
        });
        return response.text();
      })
      .then(rawText => {
        const normalizedText = absolutizeModelSetting(rawText, modelUrl);
        console.info('[pet-renderer] normalized model3 references', normalizedText);
        const bytes = new TextEncoder().encode(normalizedText);
        console.info('[pet-renderer] model3 buffer bytes', bytes.byteLength);
        const setting: ICubismModelSetting = new CubismModelSettingJson(
          bytes.buffer as ArrayBuffer,
          bytes.byteLength
        );

        // ステートを更新
        this._state = LoadStep.LoadModel;

        // 結果を保存
        this.setupModel(setting);
      })
      .catch(error => {
        // model3.json読み込みでエラーが発生した時点で描画は不可能なので、setupせずエラーをcatchして何もしない
        CubismLogError(`Failed to load file ${this._modelHomeDir}${fileName}`);
      });
  }

  /**
   * model3.jsonからモデルを生成する。
   * model3.jsonの記述に従ってモデル生成、モーション、物理演算などのコンポーネント生成を行う。
   *
   * @param setting ICubismModelSettingのインスタンス
   */
  private setupModel(setting: ICubismModelSetting): void {
    this._updating = true;
    this._initialized = false;

    this._modelSetting = setting;

    const finalizeRendererBoot = (): void => {
      this._state = LoadStep.LoadTexture;
      console.info('[pet-renderer] Finalizing minimal renderer boot');
      this._model.saveParameters();
      this._motionManager.stopAllMotions();
      this._updating = false;
      this._initialized = true;

      console.info('[pet-renderer] Creating renderer', {
        width: this._subdelegate.getCanvas().width,
        height: this._subdelegate.getCanvas().height
      });
      this.createRenderer(
        this._subdelegate.getCanvas().width,
        this._subdelegate.getCanvas().height
      );
      console.info('[pet-renderer] Setting up textures');
      this.setupTextures();
      console.info('[pet-renderer] Starting renderer');
      this.getRenderer().startUp(this._subdelegate.getGlManager().getGl());
      console.info('[pet-renderer] Loading shaders');
      this.getRenderer().loadShaders(LAppDefine.ShaderPath);
    };

    // CubismModel
    if (this._modelSetting.getModelFileName() != '') {
      const modelFileName = this._modelSetting.getModelFileName();
      const physicsFileNameForLog = safeModelSettingString(
        this._modelSetting,
        'getPhysicsFileName'
      );
      const displayInfoFileName = safeModelSettingString(
        this._modelSetting,
        'getDisplayInfoFileName'
      );
      console.info('[pet-renderer] model setting resolved paths', {
        moc: modelFileName,
        physics: physicsFileNameForLog,
        displayInfo: displayInfoFileName
      });

      fetch(this.resolveAssetPath(modelFileName), { cache: 'no-store' })
        .then(response => {
          console.info('[pet-renderer] model fetch response', {
            url: this.resolveAssetPath(modelFileName),
            status: response.status,
            ok: response.ok
          });
          if (response.ok) {
            return response.arrayBuffer();
          } else if (response.status >= 400) {
            CubismLogError(
              `Failed to load file ${this.resolveAssetPath(modelFileName)}`
            );
            return new ArrayBuffer(0);
          }
        })
        .then(arrayBuffer => {
          console.info('[pet-renderer] model buffer bytes', arrayBuffer?.byteLength);
          if (!arrayBuffer) {
            throw new Error(`Model buffer missing for ${modelFileName}`);
          }
          this.loadModel(arrayBuffer, this._mocConsistency);
          if (MINIMAL_RENDERER_BOOT) {
            console.info(
              '[pet-renderer] Minimal renderer boot enabled, skipping optional setup chain'
            );
            this._state = LoadStep.SetupLayout;
            setupLayout();
            return;
          }
          this._state = LoadStep.LoadExpression;

          // callback
          loadCubismExpression();
        });

      this._state = LoadStep.WaitLoadModel;
    } else {
      LAppPal.printMessage('Model data does not exist.');
    }

    // Expression
    const loadCubismExpression = (): void => {
      if (this._modelSetting.getExpressionCount() > 0) {
        const count: number = this._modelSetting.getExpressionCount();

        for (let i = 0; i < count; i++) {
          const expressionName = this._modelSetting.getExpressionName(i);
          const expressionFileName =
            this._modelSetting.getExpressionFileName(i);

          fetch(this.resolveAssetPath(expressionFileName), { cache: 'no-store' })
            .then(response => {
              if (response.ok) {
                return response.arrayBuffer();
              } else if (response.status >= 400) {
                CubismLogError(
                  `Failed to load file ${this.resolveAssetPath(expressionFileName)}`
                );
                // ファイルが存在しなくてもresponseはnullを返却しないため、空のArrayBufferで対応する
                return new ArrayBuffer(0);
              }
            })
            .then(arrayBuffer => {
              const motion: ACubismMotion = this.loadExpression(
                arrayBuffer,
                arrayBuffer.byteLength,
                expressionName
              );

              if (this._expressions.get(expressionName) != null) {
                ACubismMotion.delete(this._expressions.get(expressionName));
                this._expressions.set(expressionName, null);
              }

              this._expressions.set(expressionName, motion);

              this._expressionCount++;

              if (this._expressionCount >= count) {
                // Expression Updaterの追加
                if (this._expressionManager != null) {
                  const expressionUpdater = new CubismExpressionUpdater(
                    this._expressionManager
                  );
                  this._updateScheduler.addUpdatableList(expressionUpdater);
                }

                this._state = LoadStep.LoadPhysics;

                // callback
                loadCubismPhysics();
              }
            });
        }
        this._state = LoadStep.WaitLoadExpression;
      } else {
        this._state = LoadStep.LoadPhysics;

        // callback
        loadCubismPhysics();
      }
    };

    // Physics
    const loadCubismPhysics = (): void => {
      if (SKIP_OPTIONAL_PHYSICS) {
        console.info('[pet-renderer] Skipping physics during initial renderer migration');
        this._state = LoadStep.LoadPose;
        loadCubismPose();
        return;
      }

      const physicsFileName = safeModelSettingString(
        this._modelSetting,
        'getPhysicsFileName'
      );
      if (physicsFileName != '') {

        fetch(this.resolveAssetPath(physicsFileName), { cache: 'no-store' })
          .then(response => {
            console.info('[pet-renderer] physics fetch response', {
              url: this.resolveAssetPath(physicsFileName),
              status: response.status,
              ok: response.ok
            });
            if (response.ok) {
              return response.arrayBuffer();
            } else if (response.status >= 400) {
              CubismLogError(
                `Failed to load file ${this.resolveAssetPath(physicsFileName)}`
              );
              return new ArrayBuffer(0);
            }
          })
          .then(arrayBuffer => {
            console.info('[pet-renderer] physics buffer bytes', arrayBuffer?.byteLength);
            try {
              this.loadPhysics(arrayBuffer, arrayBuffer.byteLength);

              // Physics Updaterの追加
              if (this._physics) {
                const physicsUpdater = new CubismPhysicsUpdater(this._physics);
                this._updateScheduler.addUpdatableList(physicsUpdater);
              }
            } catch (error) {
              console.warn(
                '[pet-renderer] Physics load failed, continuing without physics',
                error
              );
            }

            this._state = LoadStep.LoadPose;

            // callback
            loadCubismPose();
          });
        this._state = LoadStep.WaitLoadPhysics;
      } else {
        this._state = LoadStep.LoadPose;

        // callback
        loadCubismPose();
      }
    };

    // Pose
    const loadCubismPose = (): void => {
      const poseFileName = safeModelSettingString(
        this._modelSetting,
        'getPoseFileName'
      );
      if (poseFileName != '') {

        fetch(this.resolveAssetPath(poseFileName), { cache: 'no-store' })
          .then(response => {
            console.info('[pet-renderer] pose fetch response', {
              url: this.resolveAssetPath(poseFileName),
              status: response.status,
              ok: response.ok
            });
            if (response.ok) {
              return response.arrayBuffer();
            } else if (response.status >= 400) {
              CubismLogError(
                `Failed to load file ${this.resolveAssetPath(poseFileName)}`
              );
              return new ArrayBuffer(0);
            }
          })
          .then(arrayBuffer => {
            console.info('[pet-renderer] pose buffer bytes', arrayBuffer?.byteLength);
            try {
              this.loadPose(arrayBuffer, arrayBuffer.byteLength);

              // Pose Updaterの追加
              if (this._pose) {
                const poseUpdater = new CubismPoseUpdater(this._pose);
                this._updateScheduler.addUpdatableList(poseUpdater);
              }
            } catch (error) {
              console.warn(
                '[pet-renderer] Pose load failed, continuing without pose',
                error
              );
            }

            this._state = LoadStep.SetupEyeBlink;

            // callback
            setupEyeBlink();
          });
        this._state = LoadStep.WaitLoadPose;
      } else {
        this._state = LoadStep.SetupEyeBlink;

        // callback
        setupEyeBlink();
      }
    };

    // EyeBlink
    const setupEyeBlink = (): void => {
      if (this._modelSetting.getEyeBlinkParameterCount() > 0) {
        this._eyeBlink = CubismEyeBlink.create(this._modelSetting);
        const eyeBlinkUpdater = new CubismEyeBlinkUpdater(
          () => this._motionUpdated,
          this._eyeBlink
        );
        this._updateScheduler.addUpdatableList(eyeBlinkUpdater);
      }

      this._state = LoadStep.SetupBreath;

      // callback
      setupBreath();
    };

    // Breath
    const setupBreath = (): void => {
      this._breath = CubismBreath.create();

      const breathParameters: Array<BreathParameterData> = [
        new BreathParameterData(this._idParamAngleX, 0.0, 15.0, 6.5345, 0.5),
        new BreathParameterData(this._idParamAngleY, 0.0, 8.0, 3.5345, 0.5),
        new BreathParameterData(this._idParamAngleZ, 0.0, 10.0, 5.5345, 0.5),
        new BreathParameterData(
          this._idParamBodyAngleX,
          0.0,
          4.0,
          15.5345,
          0.5
        ),
        new BreathParameterData(
          CubismFramework.getIdManager().getId(
            CubismDefaultParameterId.ParamBreath
          ),
          0.5,
          0.5,
          3.2345,
          1
        )
      ];

      this._breath.setParameters(breathParameters);

      const breathUpdater = new CubismBreathUpdater(this._breath);
      this._updateScheduler.addUpdatableList(breathUpdater);

      this._state = LoadStep.LoadUserData;

      // callback
      loadUserData();
    };

    // UserData
    const loadUserData = (): void => {
      const userDataFile = safeModelSettingString(
        this._modelSetting,
        'getUserDataFile'
      );
      if (userDataFile != '') {

      fetch(this.resolveAssetPath(userDataFile), { cache: 'no-store' })
          .then(response => {
            console.info('[pet-renderer] userdata fetch response', {
              url: this.resolveAssetPath(userDataFile),
              status: response.status,
              ok: response.ok
            });
            if (response.ok) {
              return response.arrayBuffer();
            } else if (response.status >= 400) {
              CubismLogError(
                `Failed to load file ${this.resolveAssetPath(userDataFile)}`
              );
              return new ArrayBuffer(0);
            }
          })
          .then(arrayBuffer => {
            console.info('[pet-renderer] userdata buffer bytes', arrayBuffer?.byteLength);
            try {
              this.loadUserData(arrayBuffer, arrayBuffer.byteLength);
            } catch (error) {
              console.warn(
                '[pet-renderer] UserData load failed, continuing without userdata',
                error
              );
            }

            this._state = LoadStep.SetupEyeBlinkIds;

            // callback
            setupEyeBlinkIds();
          });

        this._state = LoadStep.WaitLoadUserData;
      } else {
        this._state = LoadStep.SetupEyeBlinkIds;

        // callback
        setupEyeBlinkIds();
      }
    };

    // EyeBlinkIds
    const setupEyeBlinkIds = (): void => {
      const eyeBlinkIdCount: number =
        this._modelSetting.getEyeBlinkParameterCount();

      this._eyeBlinkIds.length = eyeBlinkIdCount;
      for (let i = 0; i < eyeBlinkIdCount; ++i) {
        this._eyeBlinkIds[i] = this._modelSetting.getEyeBlinkParameterId(i);
      }

      this._state = LoadStep.SetupLipSyncIds;

      // callback
      setupLipSyncIds();
    };

    // LipSyncIds
    const setupLipSyncIds = (): void => {
      const lipSyncIdCount = this._modelSetting.getLipSyncParameterCount();

      this._lipSyncIds.length = lipSyncIdCount;
      for (let i = 0; i < lipSyncIdCount; ++i) {
        this._lipSyncIds[i] = this._modelSetting.getLipSyncParameterId(i);
      }

      if (this._lipSyncIds.length > 0) {
        this._externalLipSyncIds = [...this._lipSyncIds];
      } else {
        this._externalLipSyncIds = LAppModel.FallbackMouthParameterIds.map(
          parameterId => CubismFramework.getIdManager().getId(parameterId)
        );
      }

      // LipSync Updaterの追加
      if (this._lipSyncIds.length > 0) {
        const lipSyncUpdater = new CubismLipSyncUpdater(
          this._lipSyncIds,
          this._wavFileHandler
        );
        this._updateScheduler.addUpdatableList(lipSyncUpdater);
      }

      this._state = LoadStep.SetupLook;

      // callback
      setupLook();
    };

    // Look
    const setupLook = (): void => {
      this._look = CubismLook.create();

      const lookParameters: Array<LookParameterData> = [
        new LookParameterData(this._idParamAngleX, 30.0, 0.0, 0.0),
        new LookParameterData(this._idParamAngleY, 0.0, 30.0, 0.0),
        new LookParameterData(this._idParamAngleZ, 0.0, 0.0, -30.0),
        new LookParameterData(this._idParamBodyAngleX, 10.0, 0.0, 0.0),
        new LookParameterData(
          CubismFramework.getIdManager().getId(
            CubismDefaultParameterId.ParamEyeBallX
          ),
          1.0,
          0.0,
          0.0
        ),
        new LookParameterData(
          CubismFramework.getIdManager().getId(
            CubismDefaultParameterId.ParamEyeBallY
          ),
          0.0,
          1.0,
          0.0
        )
      ];

      this._look.setParameters(lookParameters);

      const lookUpdater = new CubismLookUpdater(this._look, this._dragManager);
      this._updateScheduler.addUpdatableList(lookUpdater);

      // callback
      finalizeUpdaters();
    };

    // UpdateScheduler最終化処理
    const finalizeUpdaters = (): void => {
      // 全てのUpdaterが追加されたのでUpdateSchedulerを最終ソート
      this._updateScheduler.sortUpdatableList();

      this._state = LoadStep.SetupLayout;

      // callback
      setupLayout();
    };

    // Layout
    const setupLayout = (): void => {
      const layout: Map<string, number> = new Map<string, number>();

      if (this._modelSetting == null || this._modelMatrix == null) {
        CubismLogError('Failed to setupLayout().');
        return;
      }

      try {
        this._modelSetting.getLayoutMap(layout);
        if (layout.size > 0) {
          this._modelMatrix.setupFromLayout(layout);
        } else {
          console.info('[pet-renderer] No layout map found, using default model matrix');
        }
      } catch (error) {
        console.warn(
          '[pet-renderer] Layout setup failed, continuing with default model matrix',
          error
        );
      }
      if (MINIMAL_RENDERER_BOOT) {
        console.info(
          '[pet-renderer] Minimal renderer boot continuing directly to renderer setup'
        );
        finalizeRendererBoot();
        return;
      }
      this._state = LoadStep.LoadMotion;

      // callback
      loadCubismMotion();
    };

    // Motion
    const loadCubismMotion = (): void => {
      this._state = LoadStep.WaitLoadMotion;
      this._model.saveParameters();
      this._allMotionCount = 0;
      this._motionCount = 0;
      const group: string[] = [];

      const motionGroupCount: number = this._modelSetting.getMotionGroupCount();

      // モーションの総数を求める
      for (let i = 0; i < motionGroupCount; i++) {
        group[i] = this._modelSetting.getMotionGroupName(i);
        this._allMotionCount += this._modelSetting.getMotionCount(group[i]);
      }

      // モーションの読み込み
      for (let i = 0; i < motionGroupCount; i++) {
        this.preLoadMotionGroup(group[i]);
      }

      if (motionGroupCount == 0) {
        finalizeRendererBoot();
        return;
      }

      // モーションがない場合
      if (motionGroupCount == 0) {
        this._state = LoadStep.LoadTexture;

        // 全てのモーションを停止する
        this._motionManager.stopAllMotions();

        this._updating = false;
        this._initialized = true;

        this.createRenderer(
          this._subdelegate.getCanvas().width,
          this._subdelegate.getCanvas().height
        );
        this.setupTextures();
        this.getRenderer().startUp(this._subdelegate.getGlManager().getGl());
        this.getRenderer().loadShaders(LAppDefine.ShaderPath);
      }
    };
  }

  /**
   * テクスチャユニットにテクスチャをロードする
   */
  private setupTextures(): void {
    // iPhoneでのアルファ品質向上のためTypescriptではpremultipliedAlphaを採用
    const usePremultiply = true;

    if (this._state == LoadStep.LoadTexture) {
      // テクスチャ読み込み用
      const textureCount: number = this._modelSetting.getTextureCount();

      for (
        let modelTextureNumber = 0;
        modelTextureNumber < textureCount;
        modelTextureNumber++
      ) {
        // テクスチャ名が空文字だった場合はロード・バインド処理をスキップ
        if (this._modelSetting.getTextureFileName(modelTextureNumber) == '') {
          console.log('getTextureFileName null');
          continue;
        }

        // WebGLのテクスチャユニットにテクスチャをロードする
        let texturePath =
          this._modelSetting.getTextureFileName(modelTextureNumber);
        texturePath = this.resolveAssetPath(texturePath);

        // ロード完了時に呼び出すコールバック関数
        const onLoad = (textureInfo: TextureInfo): void => {
          this.getRenderer().bindTexture(modelTextureNumber, textureInfo.id);

          this._textureCount++;

          if (this._textureCount >= textureCount) {
            // ロード完了
            this._state = LoadStep.CompleteSetup;
          }
        };

        // 読み込み
        this._subdelegate
          .getTextureManager()
          .createTextureFromPngFile(texturePath, usePremultiply, onLoad);
        this.getRenderer().setIsPremultipliedAlpha(usePremultiply);
      }

      this._state = LoadStep.WaitLoadTexture;
    }
  }

  /**
   * レンダラを再構築する
   */
  public reloadRenderer(): void {
    this.deleteRenderer();
    this.createRenderer(
      this._subdelegate.getCanvas().width,
      this._subdelegate.getCanvas().height
    );
    this.setupTextures();
  }

  /**
   * 更新
   */
  public update(): void {
    if (this._state != LoadStep.CompleteSetup) return;

    const deltaTimeSeconds: number = LAppPal.getDeltaTime();
    this._userTimeSeconds += deltaTimeSeconds;

    //--------------------------------------------------------------------------
    this._model.loadParameters(); // 前回セーブされた状態をロード

    // Reset motion updated flag each frame
    this._motionUpdated = false;

    if (
      this._motionManager.isFinished() &&
      this._modelSetting.getMotionCount(LAppDefine.MotionGroupIdle) > 0
    ) {
      // モーションの再生がない場合、待機モーションの中からランダムで再生する
      this.startRandomMotion(
        LAppDefine.MotionGroupIdle,
        LAppDefine.PriorityIdle
      );
    } else if (!this._motionManager.isFinished()) {
      this._motionUpdated = this._motionManager.updateMotion(
        this._model,
        deltaTimeSeconds
      ); // モーションを更新
    }
    this._model.saveParameters(); // 状態を保存
    //--------------------------------------------------------------------------

    // UpdateSchedulerによる一括エフェクト更新
    this._updateScheduler.onLateUpdate(this._model, deltaTimeSeconds);
    this.applyFallbackIdle();
    this.applyIdleBlink(deltaTimeSeconds);
    this.applyExternalLookTarget(deltaTimeSeconds);
    this.applyExternalLipSync();
    this.applyExternalParameterTargets(deltaTimeSeconds);
    this.applyMouthDebugPulse(deltaTimeSeconds);

    this._model.update();
  }

  public setExternalLipSyncValue(value: number): void {
    const nextValue = clamp01(value);
    this._externalLipSyncActive =
      nextValue > 0.001 || this._externalLipSyncValue > 0.001;
    this._externalLipSyncValue = nextValue;
  }

  public startMouthDebugPulse(durationSeconds = 3): void {
    this._mouthDebugPulseElapsed = 0;
    this._mouthDebugPulseDuration = Math.max(0.1, durationSeconds);
    this._mouthDebugPulseActive = true;
  }

  public setExternalLookTarget(x: number, y: number): void {
    this._externalLookTargetX = clampSigned(x);
    this._externalLookTargetY = clampSigned(y);
  }

  public setExternalParameterTarget(
    parameterId: string,
    targetValue: number,
    durationSeconds = 0.85,
    parameterIndex: number | null = null
  ): void {
    const normalizedIndex =
      Number.isInteger(parameterIndex) && parameterIndex !== null && parameterIndex >= 0
        ? parameterIndex
        : null;
    const normalizedParameterId = String(parameterId || "").trim();
    const key =
      normalizedIndex !== null
        ? `index:${normalizedIndex}`
        : normalizedParameterId;
    if (!key) {
      return;
    }

    const existing = this._externalParameterTargets.get(key);
    this._externalParameterTargets.set(key, {
      id:
        normalizedIndex === null
          ? existing?.id || CubismFramework.getIdManager().getId(normalizedParameterId)
          : null,
      parameterIndex: normalizedIndex,
      currentValue: existing?.currentValue ?? 0,
      targetValue: clampExternalParameterValue(targetValue),
      durationSeconds: Math.max(0.08, durationSeconds)
    });
  }

  public isReadyToRender(): boolean {
    if (this._model == null || this._state != LoadStep.CompleteSetup) {
      return false;
    }

    try {
      const renderer = this.getRenderer() as unknown as
        | { gl?: WebGLRenderingContext | WebGL2RenderingContext }
        | null;
      const gl = renderer?.gl;

      if (!gl) {
        return false;
      }

      return !!CubismShaderManager_WebGL.getInstance().getShader(gl)?._isShaderLoaded;
    } catch (error) {
      console.warn('[pet-renderer] Shader readiness check failed', error);
      return false;
    }
  }

  /**
   * 引数で指定したモーションの再生を開始する
   * @param group モーショングループ名
   * @param no グループ内の番号
   * @param priority 優先度
   * @param onFinishedMotionHandler モーション再生終了時に呼び出されるコールバック関数
   * @return 開始したモーションの識別番号を返す。個別のモーションが終了したか否かを判定するisFinished()の引数で使用する。開始できない時は[-1]
   */
  public startMotion(
    group: string,
    no: number,
    priority: number,
    onFinishedMotionHandler?: FinishedMotionCallback,
    onBeganMotionHandler?: BeganMotionCallback
  ): CubismMotionQueueEntryHandle {
    if (priority == LAppDefine.PriorityForce) {
      this._motionManager.setReservePriority(priority);
    } else if (!this._motionManager.reserveMotion(priority)) {
      if (this._debugMode) {
        LAppPal.printMessage("[APP]can't start motion.");
      }
      return InvalidMotionQueueEntryHandleValue;
    }

    const motionFileName = this._modelSetting.getMotionFileName(group, no);

    // ex) idle_0
    const name = `${group}_${no}`;
    let motion: CubismMotion = this._motions.get(name) as CubismMotion;
    let autoDelete = false;

    if (motion == null) {
      fetch(this.resolveAssetPath(motionFileName), { cache: 'no-store' })
        .then(response => {
          if (response.ok) {
            return response.arrayBuffer();
          } else if (response.status >= 400) {
            CubismLogError(
              `Failed to load file ${this.resolveAssetPath(motionFileName)}`
            );
            return new ArrayBuffer(0);
          }
        })
        .then(arrayBuffer => {
          motion = this.loadMotion(
            arrayBuffer,
            arrayBuffer.byteLength,
            null,
            onFinishedMotionHandler,
            onBeganMotionHandler,
            this._modelSetting,
            group,
            no,
            this._motionConsistency
          );
        });

      if (motion) {
        motion.setEffectIds(this._eyeBlinkIds, this._lipSyncIds);
        autoDelete = true; // 終了時にメモリから削除
      } else {
        CubismLogError("Can't start motion {0} .", motionFileName);
        // ロードできなかったモーションのReservePriorityをリセットする
        this._motionManager.setReservePriority(LAppDefine.PriorityNone);
        return InvalidMotionQueueEntryHandleValue;
      }
    } else {
      motion.setBeganMotionHandler(onBeganMotionHandler);
      motion.setFinishedMotionHandler(onFinishedMotionHandler);
    }

    //voice
    const voice = this._modelSetting.getMotionSoundFileName(group, no);
    if (voice.localeCompare('') != 0) {
      let path = voice;
      path = this._modelHomeDir + path;
      this._wavFileHandler.start(path);
    }

    if (this._debugMode) {
      LAppPal.printMessage(`[APP]start motion: [${group}_${no}]`);
    }
    return this._motionManager.startMotionPriority(
      motion,
      autoDelete,
      priority
    );
  }

  /**
   * ランダムに選ばれたモーションの再生を開始する。
   * @param group モーショングループ名
   * @param priority 優先度
   * @param onFinishedMotionHandler モーション再生終了時に呼び出されるコールバック関数
   * @return 開始したモーションの識別番号を返す。個別のモーションが終了したか否かを判定するisFinished()の引数で使用する。開始できない時は[-1]
   */
  public startRandomMotion(
    group: string,
    priority: number,
    onFinishedMotionHandler?: FinishedMotionCallback,
    onBeganMotionHandler?: BeganMotionCallback
  ): CubismMotionQueueEntryHandle {
    if (this._modelSetting.getMotionCount(group) == 0) {
      return InvalidMotionQueueEntryHandleValue;
    }

    const no: number = Math.floor(
      Math.random() * this._modelSetting.getMotionCount(group)
    );

    return this.startMotion(
      group,
      no,
      priority,
      onFinishedMotionHandler,
      onBeganMotionHandler
    );
  }

  /**
   * 引数で指定した表情モーションをセットする
   *
   * @param expressionId 表情モーションのID
   */
  public setExpression(expressionId: string): void {
    const motion: ACubismMotion = this._expressions.get(expressionId);

    if (this._debugMode) {
      LAppPal.printMessage(`[APP]expression: [${expressionId}]`);
    }

    if (motion != null) {
      this._expressionManager.startMotion(motion, false);
    } else {
      if (this._debugMode) {
        LAppPal.printMessage(`[APP]expression[${expressionId}] is null`);
      }
    }
  }

  /**
   * ランダムに選ばれた表情モーションをセットする
   */
  public setRandomExpression(): void {
    if (this._expressions.size == 0) {
      return;
    }

    const no: number = Math.floor(Math.random() * this._expressions.size);

    for (let i = 0; i < this._expressions.size; i++) {
      if (i == no) {
        // const name: string = this._expressions._keyValues[i].first;
        const expressionsArray = [...this._expressions.entries()];
        const name: string = expressionsArray[i][0];
        this.setExpression(name);
        return;
      }
    }
  }

  /**
   * イベントの発火を受け取る
   */
  public motionEventFired(eventValue: string): void {
    CubismLogInfo('{0} is fired on LAppModel!!', eventValue);
  }

  /**
   * 当たり判定テスト
   * 指定ＩＤの頂点リストから矩形を計算し、座標をが矩形範囲内か判定する。
   *
   * @param hitArenaName  当たり判定をテストする対象のID
   * @param x             判定を行うX座標
   * @param y             判定を行うY座標
   */
  public hitTest(hitArenaName: string, x: number, y: number): boolean {
    // 透明時は当たり判定無し。
    if (this._opacity < 1) {
      return false;
    }

    const count: number = this._modelSetting.getHitAreasCount();

    for (let i = 0; i < count; i++) {
      if (this._modelSetting.getHitAreaName(i) == hitArenaName) {
        const drawId: CubismIdHandle = this._modelSetting.getHitAreaId(i);
        return this.isHit(drawId, x, y);
      }
    }

    return false;
  }

  /**
   * モーションデータをグループ名から一括でロードする。
   * モーションデータの名前は内部でModelSettingから取得する。
   *
   * @param group モーションデータのグループ名
   */
  public preLoadMotionGroup(group: string): void {
    for (let i = 0; i < this._modelSetting.getMotionCount(group); i++) {
      const motionFileName = this._modelSetting.getMotionFileName(group, i);

      // ex) idle_0
      const name = `${group}_${i}`;
      if (this._debugMode) {
        LAppPal.printMessage(
          `[APP]load motion: ${motionFileName} => [${name}]`
        );
      }

      fetch(this.resolveAssetPath(motionFileName), { cache: 'no-store' })
        .then(response => {
          if (response.ok) {
            return response.arrayBuffer();
          } else if (response.status >= 400) {
            CubismLogError(
              `Failed to load file ${this.resolveAssetPath(motionFileName)}`
            );
            return new ArrayBuffer(0);
          }
        })
        .then(arrayBuffer => {
          const tmpMotion: CubismMotion = this.loadMotion(
            arrayBuffer,
            arrayBuffer.byteLength,
            name,
            null,
            null,
            this._modelSetting,
            group,
            i,
            this._motionConsistency
          );

          if (tmpMotion != null) {
            tmpMotion.setEffectIds(this._eyeBlinkIds, this._lipSyncIds);

            if (this._motions.get(name) != null) {
              ACubismMotion.delete(this._motions.get(name));
            }

            this._motions.set(name, tmpMotion);

            this._motionCount++;
          } else {
            // loadMotionできなかった場合はモーションの総数がずれるので1つ減らす
            this._allMotionCount--;
          }

          if (this._motionCount >= this._allMotionCount) {
            this._state = LoadStep.LoadTexture;

            // 全てのモーションを停止する
            this._motionManager.stopAllMotions();

            this._updating = false;
            this._initialized = true;

            this.createRenderer(
              this._subdelegate.getCanvas().width,
              this._subdelegate.getCanvas().height
            );
            this.setupTextures();
            this.getRenderer().startUp(
              this._subdelegate.getGlManager().getGl()
            );
            this.getRenderer().loadShaders(LAppDefine.ShaderPath);
          }
        });
    }
  }

  /**
   * すべてのモーションデータを解放する。
   */
  public releaseMotions(): void {
    this._motions.clear();
  }

  /**
   * 全ての表情データを解放する。
   */
  public releaseExpressions(): void {
    this._expressions.clear();
  }

  /**
   * モデルを描画する処理。モデルを描画する空間のView-Projection行列を渡す。
   */
  public doDraw(): void {
    if (this._model == null) return;

    // キャンバスサイズを渡す
    const canvas = this._subdelegate.getCanvas();
    const viewport: number[] = [0, 0, canvas.width, canvas.height];

    this.getRenderer().setRenderState(
      this._subdelegate.getFrameBuffer(),
      viewport
    );
    this.getRenderer().drawModel(LAppDefine.ShaderPath);
  }

  /**
   * モデルを描画する処理。モデルを描画する空間のView-Projection行列を渡す。
   */
  public draw(matrix: CubismMatrix44): void {
    if (this._model == null) {
      return;
    }

    // 各読み込み終了後
    if (this._state == LoadStep.CompleteSetup) {
      matrix.multiplyByMatrix(this._modelMatrix);

      this.getRenderer().setMvpMatrix(matrix);

      this.doDraw();
    }
  }

  public async hasMocConsistencyFromFile() {
    CSM_ASSERT(this._modelSetting.getModelFileName().localeCompare(``));

    // CubismModel
    if (this._modelSetting.getModelFileName() != '') {
      const modelFileName = this._modelSetting.getModelFileName();

      const response = await fetch(this.resolveAssetPath(modelFileName), { cache: 'no-store' });
      const arrayBuffer = await response.arrayBuffer();

      this._consistency = CubismMoc.hasMocConsistency(arrayBuffer);

      if (!this._consistency) {
        CubismLogInfo('Inconsistent MOC3.');
      } else {
        CubismLogInfo('Consistent MOC3.');
      }

      return this._consistency;
    } else {
      LAppPal.printMessage('Model data does not exist.');
    }
  }

  public setSubdelegate(subdelegate: LAppSubdelegate): void {
    this._subdelegate = subdelegate;
  }

  private isExistingParameter(parameterId: CubismIdHandle): boolean {
    if (!this._model) {
      return false;
    }

    const parameterIndex = this._model.getParameterIndex(parameterId);
    return parameterIndex >= 0 && parameterIndex < this._model.getParameterCount();
  }

  private setExistingParameterValue(
    parameterId: CubismIdHandle,
    value: number,
    weight = 1.0
  ): void {
    if (!this.isExistingParameter(parameterId)) {
      return;
    }
    this._model.setParameterValueById(parameterId, value, weight);
  }

  private addExistingParameterValue(
    parameterId: CubismIdHandle,
    value: number,
    weight = 1.0
  ): void {
    if (!this.isExistingParameter(parameterId)) {
      return;
    }
    this._model.addParameterValueById(parameterId, value, weight);
  }

  private applyFallbackIdle(): void {
    if (!this._model) {
      return;
    }

    const time = this._userTimeSeconds;
    const hasIdleMotion =
      this._modelSetting?.getMotionCount(LAppDefine.MotionGroupIdle) > 0;
    const weight = hasIdleMotion ? 0.22 : 0.86;

    this.addExistingParameterValue(
      this._idParamAngleX,
      Math.sin(time * 0.72) * 12.5,
      weight
    );
    this.addExistingParameterValue(
      this._idParamAngleY,
      Math.sin(time * 0.48 + 0.8) * 8.0,
      weight
    );
    this.addExistingParameterValue(
      this._idParamAngleZ,
      Math.sin(time * 0.58 + 1.7) * 9.2,
      weight
    );
    this.addExistingParameterValue(
      this._idParamBodyAngleX,
      Math.sin(time * 0.38 + 0.4) * 8.5,
      weight
    );
    this.addExistingParameterValue(
      this._idParamBodyAngleY,
      Math.sin(time * 0.42 + 1.2) * 5.8,
      weight
    );
    this.addExistingParameterValue(
      this._idParamBodyAngleZ,
      Math.sin(time * 0.35 + 2.0) * 5.6,
      weight
    );
    this.addExistingParameterValue(
      this._idParamChestX,
      Math.sin(time * 0.56 + 0.35) * 8.0,
      weight
    );
    this.addExistingParameterValue(
      this._idParamChestY,
      Math.sin(time * 0.72 + 1.1) * 10.5,
      weight
    );

    for (const parameter of this._secondaryIdleWaveParameters) {
      this.addExistingParameterValue(
        parameter.id,
        Math.sin(time * parameter.speed + parameter.phase) * parameter.amplitude,
        weight * parameter.weightScale
      );
    }
  }

  private scheduleNextIdleBlink(): void {
    this._idleBlinkElapsed = 0;
    this._idleBlinkInterval = 1.6 + Math.random() * 2.2;
    this._idleBlinkDuration = 0.24 + Math.random() * 0.08;
    this._idleBlinkDouble = Math.random() < 0.22;
  }

  private getIdleBlinkOpenValue(progress: number): number {
    if (progress < 0 || progress > 1) {
      return 1;
    }

    if (this._idleBlinkDouble) {
      if (progress < 0.18) {
        return 1 - progress / 0.18;
      }
      if (progress < 0.34) {
        return 0;
      }
      if (progress < 0.52) {
        return (progress - 0.34) / 0.18;
      }
      if (progress < 0.64) {
        return 1 - (progress - 0.52) / 0.12;
      }
      if (progress < 0.8) {
        return 0;
      }
      return (progress - 0.8) / 0.2;
    }

    if (progress < 0.28) {
      return 1 - progress / 0.28;
    }
    if (progress < 0.46) {
      return 0;
    }
    return (progress - 0.46) / 0.54;
  }

  private applyIdleBlink(deltaTimeSeconds: number): void {
    if (!this._model || this._idleBlinkIds.length === 0) {
      return;
    }

    this._idleBlinkElapsed += deltaTimeSeconds;
    if (this._idleBlinkElapsed < this._idleBlinkInterval) {
      return;
    }

    const blinkTime = this._idleBlinkElapsed - this._idleBlinkInterval;
    const duration = this._idleBlinkDouble
      ? this._idleBlinkDuration * 2.35
      : this._idleBlinkDuration;
    const progress = blinkTime / duration;

    if (progress >= 1) {
      for (const parameterId of this._idleBlinkIds) {
        this.setExistingParameterValue(parameterId, 1, 1.0);
      }
      this.scheduleNextIdleBlink();
      return;
    }

    const openValue = this.getIdleBlinkOpenValue(progress);
    for (const parameterId of this._idleBlinkIds) {
      this.setExistingParameterValue(parameterId, openValue, 1.0);
    }
  }

  private applyExternalLookTarget(deltaTimeSeconds: number): void {
    if (!this._model) {
      return;
    }

    const follow = Math.min(1, Math.max(0.08, deltaTimeSeconds * 12));
    this._externalLookX +=
      (this._externalLookTargetX - this._externalLookX) * follow;
    this._externalLookY +=
      (this._externalLookTargetY - this._externalLookY) * follow;

    const lookX = this._externalLookX;
    const lookY = this._externalLookY;
    if (Math.abs(lookX) < 0.002 && Math.abs(lookY) < 0.002) {
      return;
    }

    this.addExistingParameterValue(this._idParamAngleX, lookX * 22.0, 0.9);
    this.addExistingParameterValue(this._idParamAngleY, lookY * 16.0, 0.9);
    this.addExistingParameterValue(this._idParamAngleZ, -lookX * lookY * 12.0, 0.9);
    this.addExistingParameterValue(this._idParamBodyAngleX, lookX * 6.0, 0.75);
    this.addExistingParameterValue(this._idParamBodyAngleY, lookY * 3.0, 0.75);
  }

  private applyExternalLipSync(): void {
    if (!this._model || !this._externalLipSyncActive) {
      return;
    }

    const value = clamp01(this._externalLipSyncValue);
    if (value <= 0.001) {
      for (const parameterId of this.getMouthParameterIds()) {
        this.setExistingParameterValue(parameterId, 0, 1.0);
      }
      this._externalLipSyncActive = false;
      return;
    }

    const time = this._userTimeSeconds;
    const drive = Math.max(0.45, value);
    const primaryWave = 0.5 + 0.5 * Math.sin(time * 18.0);
    const secondaryWave = 0.5 + 0.5 * Math.sin(time * 31.0 + 0.7);
    const speechPulse = 0.2 + 0.58 * primaryWave + 0.22 * secondaryWave;
    const mouthOpenValue = Math.min(2.1, drive * speechPulse * 2.1);
    for (const parameterId of this.getMouthParameterIds()) {
      this.setExistingParameterValue(parameterId, mouthOpenValue, 1.0);
    }
  }

  private applyExternalParameterTargets(deltaTimeSeconds: number): void {
    if (!this._model || this._externalParameterTargets.size === 0) {
      return;
    }

    for (const parameter of this._externalParameterTargets.values()) {
      const follow = Math.min(
        1,
        Math.max(0.02, deltaTimeSeconds / parameter.durationSeconds)
      );
      parameter.currentValue +=
        (parameter.targetValue - parameter.currentValue) * follow;
      if (Math.abs(parameter.targetValue - parameter.currentValue) < 0.001) {
        parameter.currentValue = parameter.targetValue;
      }
      if (parameter.parameterIndex !== null) {
        if (
          parameter.parameterIndex >= 0 &&
          parameter.parameterIndex < this._model.getParameterCount()
        ) {
          this._model.setParameterValueByIndex(
            parameter.parameterIndex,
            parameter.currentValue,
            1.0
          );
        }
      } else if (parameter.id) {
        this.setExistingParameterValue(parameter.id, parameter.currentValue, 1.0);
      }
    }
  }

  private getMouthParameterIds(): Array<CubismIdHandle> {
    if (this._externalLipSyncIds.length > 0) {
      return this._externalLipSyncIds;
    }

    return LAppModel.FallbackMouthParameterIds.map(parameterId =>
      CubismFramework.getIdManager().getId(parameterId)
    );
  }

  private applyMouthDebugPulse(deltaTimeSeconds: number): void {
    if (!this._model || !this._mouthDebugPulseActive) {
      return;
    }

    this._mouthDebugPulseElapsed += deltaTimeSeconds;
    const progress =
      this._mouthDebugPulseElapsed / this._mouthDebugPulseDuration;

    if (progress >= 1) {
      for (const parameterId of this.getMouthParameterIds()) {
        this.setExistingParameterValue(parameterId, 0, 1.0);
      }
      this._mouthDebugPulseActive = false;
      return;
    }

    const openValue = Math.max(0, Math.sin(progress * Math.PI * 8)) * 2.1;
    for (const parameterId of this.getMouthParameterIds()) {
      this.setExistingParameterValue(parameterId, openValue, 1.0);
    }
  }

  /**
   * デストラクタに相当する処理のオーバーライド
   */
  public release(): void {
    if (this._look) {
      CubismLook.delete(this._look);
      this._look = null;
    }
    if (this._updateScheduler) {
      this._updateScheduler.release();
    }
    super.release();
  }

  /**
   * コンストラクタ
   */
  public constructor() {
    super();

    this._modelSetting = null;
    this._modelHomeDir = null;
    this._assetCacheBust = '';
    this._userTimeSeconds = 0.0;

    this._eyeBlinkIds = new Array<CubismIdHandle>();
    this._lipSyncIds = new Array<CubismIdHandle>();

    this._motions = new Map<string, ACubismMotion>();
    this._expressions = new Map<string, ACubismMotion>();

    this._hitArea = new Array<csmRect>();
    this._userArea = new Array<csmRect>();

    this._idParamAngleX = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamAngleX
    );
    this._idParamAngleY = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamAngleY
    );
    this._idParamAngleZ = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamAngleZ
    );
    this._idParamBodyAngleX = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamBodyAngleX
    );
    this._idParamBodyAngleY = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamBodyAngleY
    );
    this._idParamBodyAngleZ = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamBodyAngleZ
    );
    this._idParamChestX = CubismFramework.getIdManager().getId('Param89');
    this._idParamChestY = CubismFramework.getIdManager().getId('Param90');
    this._idleBlinkIds = LAppModel.FallbackEyeBlinkParameterIds.map(
      parameterId => CubismFramework.getIdManager().getId(parameterId)
    );
    this._secondaryIdleWaveParameters =
      LAppModel.SecondaryIdleWaveParameterSpecs.map(spec => ({
        id: CubismFramework.getIdManager().getId(spec.parameterId),
        amplitude: spec.amplitude,
        speed: spec.speed,
        phase: spec.phase,
        weightScale: spec.weightScale
      }));

    if (LAppDefine.MOCConsistencyValidationEnable) {
      this._mocConsistency = true;
    }

    if (LAppDefine.MotionConsistencyValidationEnable) {
      this._motionConsistency = true;
    }

    this._state = LoadStep.LoadAssets;
    this._expressionCount = 0;
    this._textureCount = 0;
    this._motionCount = 0;
    this._allMotionCount = 0;
    this._wavFileHandler = new LAppWavFileHandler();
    this._consistency = false;
    this._look = null;
    this._updateScheduler = new CubismUpdateScheduler();
    this._motionUpdated = false;
    this._externalLipSyncIds = new Array<CubismIdHandle>();
    this._externalLipSyncValue = 0;
    this._externalLipSyncActive = false;
    this._mouthDebugPulseActive = false;
    this._mouthDebugPulseElapsed = 0;
    this._mouthDebugPulseDuration = 0;
    this._externalParameterTargets = new Map<string, ExternalParameterTarget>();
    this._externalLookTargetX = 0;
    this._externalLookTargetY = 0;
    this._externalLookX = 0;
    this._externalLookY = 0;
    this._idleBlinkElapsed = 0;
    this._idleBlinkInterval = 1.6 + Math.random() * 0.9;
    this._idleBlinkDuration = 0.26;
    this._idleBlinkDouble = false;
  }

  private _updateScheduler: CubismUpdateScheduler; // アップデートスケジューラー
  private _motionUpdated: boolean; // モーション更新フラグ
  private _subdelegate: LAppSubdelegate; // サブデリゲート

  _modelSetting: ICubismModelSetting; // モデルセッティング情報
  _modelHomeDir: string; // モデルセッティングが置かれたディレクトリ
  _userTimeSeconds: number; // デルタ時間の積算値[秒]

  _eyeBlinkIds: Array<CubismIdHandle>; // モデルに設定された瞬き機能用パラメータID
  _lipSyncIds: Array<CubismIdHandle>; // モデルに設定されたリップシンク機能用パラメータID

  _motions: Map<string, ACubismMotion>; // 読み込まれているモーションのリスト
  _expressions: Map<string, ACubismMotion>; // 読み込まれている表情のリスト

  _hitArea: Array<csmRect>;
  _userArea: Array<csmRect>;

  _idParamAngleX: CubismIdHandle; // パラメータID: ParamAngleX
  _idParamAngleY: CubismIdHandle; // パラメータID: ParamAngleY
  _idParamAngleZ: CubismIdHandle; // パラメータID: ParamAngleZ
  _idParamBodyAngleX: CubismIdHandle; // パラメータID: ParamBodyAngleX
  _idParamBodyAngleY: CubismIdHandle; // パラメータID: ParamBodyAngleY
  _idParamBodyAngleZ: CubismIdHandle; // パラメータID: ParamBodyAngleZ
  _idParamChestX: CubismIdHandle; // kuro胸部パラメータID: Param89
  _idParamChestY: CubismIdHandle; // kuro胸部パラメータID: Param90
  _idleBlinkIds: Array<CubismIdHandle>; // 明示まばたき用パラメータID
  _secondaryIdleWaveParameters: Array<IdleWaveParameter>; // 髮/裙擺/蝴蝶結の待機二次動作
  _externalLipSyncIds: Array<CubismIdHandle>; // 外部TTS音量から操作する口パラメータID
  _externalLipSyncValue: number; // 外部TTS音量から算出した口開度
  _externalLipSyncActive: boolean; // 口パラメータの明示更新が必要か
  _externalLookTargetX: number; // 外部ポインター入力から算出した目標X
  _externalLookTargetY: number; // 外部ポインター入力から算出した目標Y
  _externalLookX: number; // 補間済みの外部ポインターX
  _externalLookY: number; // 補間済みの外部ポインターY
  _idleBlinkElapsed: number; // 待機まばたきの経過時間
  _idleBlinkInterval: number; // 次のまばたきまでの秒数
  _idleBlinkDuration: number; // まばたき一回分の秒数
  _idleBlinkDouble: boolean; // 二連まばたきを行うか

  _look: CubismLook; // ドラッグ追従

  _state: LoadStep; // 現在のステータス管理用
  _expressionCount: number; // 表情データカウント
  _textureCount: number; // テクスチャカウント
  _motionCount: number; // モーションデータカウント
  _allMotionCount: number; // モーション総数
  _wavFileHandler: LAppWavFileHandler; //wavファイルハンドラ
  _consistency: boolean; // MOC3整合性チェック管理用
}
