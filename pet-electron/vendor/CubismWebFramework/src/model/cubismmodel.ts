/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

import { CubismIdHandle } from '../id/cubismid';
import { CubismFramework } from '../live2dcubismframework';
import { CubismMath } from '../math/cubismmath';
import {
  CubismBlendMode,
  CubismTextureColor
} from '../rendering/cubismrenderer';
import { CSM_ASSERT } from '../utils/cubismdebug';
import { CubismModelMultiplyAndScreenColor } from './cubismmodelmultiplyandscreencolor';

export const NoParentIndex = -1; // 親が取得できない場合の値を表す定数
export const NoOffscreenIndex = -1; // オフスクリーンが取得できない場合の値を表す定数

// Migration switch for the custom pet renderer:
// keep rendering on the simplest legacy-compatible path until the
// new Web renderer is fully stable, then re-enable advanced blend/offscreen.
const DISABLE_ADVANCED_BLEND_AND_OFFSCREENS = true;
/**
 * カラーブレンドのタイプ
 */
export enum CubismColorBlend {
  ColorBlend_None = -1,
  ColorBlend_Normal = Live2DCubismCore.ColorBlendType_Normal,
  ColorBlend_AddGlow = Live2DCubismCore.ColorBlendType_AddGlow,
  ColorBlend_Add = Live2DCubismCore.ColorBlendType_Add,
  ColorBlend_Darken = Live2DCubismCore.ColorBlendType_Darken,
  ColorBlend_Multiply = Live2DCubismCore.ColorBlendType_Multiply,
  ColorBlend_ColorBurn = Live2DCubismCore.ColorBlendType_ColorBurn,
  ColorBlend_LinearBurn = Live2DCubismCore.ColorBlendType_LinearBurn,
  ColorBlend_Lighten = Live2DCubismCore.ColorBlendType_Lighten,
  ColorBlend_Screen = Live2DCubismCore.ColorBlendType_Screen,
  ColorBlend_ColorDodge = Live2DCubismCore.ColorBlendType_ColorDodge,
  ColorBlend_Overlay = Live2DCubismCore.ColorBlendType_Overlay,
  ColorBlend_SoftLight = Live2DCubismCore.ColorBlendType_SoftLight,
  ColorBlend_HardLight = Live2DCubismCore.ColorBlendType_HardLight,
  ColorBlend_LinearLight = Live2DCubismCore.ColorBlendType_LinearLight,
  ColorBlend_Hue = Live2DCubismCore.ColorBlendType_Hue,
  ColorBlend_Color = Live2DCubismCore.ColorBlendType_Color,
  // Cubism 5.2以前
  ColorBlend_AddCompatible = Live2DCubismCore.ColorBlendType_AddCompatible,
  ColorBlend_MultiplyCompatible = Live2DCubismCore.ColorBlendType_MultiplyCompatible
}

/**
 * アルファブレンドのタイプ
 */
export enum CubismAlphaBlend {
  AlphaBlend_None = -1,
  AlphaBlend_Over,
  AlphaBlend_Atop,
  AlphaBlend_Out,
  AlphaBlend_ConjointOver,
  AlphaBlend_DisjointOver
}

/**
 * オブジェクトのタイプ
 */
export enum CubismModelObjectType {
  CubismModelObjectType_Drawable = 0,
  CubismModelObjectType_Parts = 1
}

/**
 * Structure for managing the override of parameter repetition settings
 */
export class ParameterRepeatData {
  /**
   * Constructor
   *
   * @param isOverridden whether to be overriden
   * @param isParameterRepeated override flag for settings
   */
  public constructor(
    isOverridden: boolean = false,
    isParameterRepeated: boolean = false
  ) {
    this.isOverridden = isOverridden;
    this.isParameterRepeated = isParameterRepeated;
  }

  /**
   * Whether to be overridden
   */
  public isOverridden: boolean;

  /**
   * Override flag for settings
   */
  public isParameterRepeated: boolean;
}

/**
 * (deprecated) テクスチャのカリング設定を管理するための構造体
 */
export class DrawableCullingData {
  /**
   * コンストラクタ
   *
   * @param isOverridden
   * @param isCulling
   */
  public constructor(isOverridden = false, isCulling = false) {
    this.isOverridden = isOverridden;
    this.isCulling = isCulling;
  }

  public isOverridden: boolean;
  public isCulling: boolean;

  get isOverwritten(): boolean {
    return this.isOverridden;
  }
}

/**
 * テクスチャのカリング設定を管理するための構造体
 */
export class CullingData {
  /**
   * コンストラクタ
   *
   * @param isOverridden
   * @param isCulling
   */
  public constructor(isOverridden = false, isCulling = false) {
    this.isOverridden = isOverridden;
    this.isCulling = isCulling;
  }

  public isOverridden: boolean;
  public isCulling: boolean;
}

/**
 * パーツ子描画オブジェクト情報構造体
 */
export class PartChildDrawObjects {
  public drawableIndices: Array<number>;
  public offscreenIndices: Array<number>;

  constructor(
    drawableIndices: Array<number> = new Array<number>(),
    offscreenIndices: Array<number> = new Array<number>()
  ) {
    this.drawableIndices = drawableIndices;
    this.offscreenIndices = offscreenIndices;
  }
}

/**
 * オブジェクト情報構造体
 */
export class CubismModelObjectInfo {
  public objectType: CubismModelObjectType; // オブジェクトのタイプ (Drawable / Parts)
  public objectIndex: number; // オブジェクトインデックス

  constructor(objectIndex: number, objectType: CubismModelObjectType) {
    this.objectIndex = objectIndex;
    this.objectType = objectType;
  }
}

/**
 * パーツ情報管理構造体
 */
export class CubismModelPartInfo {
  public objects: Array<CubismModelObjectInfo>;
  public childDrawObjects: PartChildDrawObjects;

  constructor(
    objects: Array<CubismModelObjectInfo> = new Array<CubismModelObjectInfo>(),
    childDrawObjects: PartChildDrawObjects = new PartChildDrawObjects()
  ) {
    this.objects = objects;
    this.childDrawObjects = childDrawObjects;
  }

  // 子オブジェクト数を返す関数
  public getChildObjectCount(): number {
    return this.objects.length;
  }
}

/**
 * モデル
 *
 * Mocデータから生成されるモデルのクラス。
 */
export class CubismModel {
  private getCoreParameters(): {
    count: number;
    ids: string[];
    values: Float32Array;
    maximumValues: Float32Array;
    minimumValues: Float32Array;
    defaultValues: Float32Array;
    types: Live2DCubismCore.csmParameterType[];
    repeats: Uint8Array;
  } {
    const parameters = (this._model as Live2DCubismCore.Model & {
      parameters?: {
        count?: number;
        ids?: string[];
        values?: Float32Array;
        maximumValues?: Float32Array;
        minimumValues?: Float32Array;
        defaultValues?: Float32Array;
        types?: Live2DCubismCore.csmParameterType[];
        repeats?: Uint8Array;
      };
    }).parameters;

    const ids = parameters?.ids ?? [];
    const values = parameters?.values ?? new Float32Array(0);
    const count = parameters?.count ?? ids.length ?? values.length ?? 0;

    return {
      count,
      ids,
      values,
      maximumValues: parameters?.maximumValues ?? new Float32Array(0),
      minimumValues: parameters?.minimumValues ?? new Float32Array(0),
      defaultValues: parameters?.defaultValues ?? new Float32Array(0),
      types: parameters?.types ?? [],
      repeats: parameters?.repeats ?? new Uint8Array(count)
    };
  }

  private getCoreParts(): {
    count: number;
    ids: string[];
    opacities: Float32Array;
    parentIndices: Int32Array;
    offscreenIndices: Int32Array;
  } {
    const parts = (this._model as Live2DCubismCore.Model & {
      parts?: {
        count?: number;
        ids?: string[];
        opacities?: Float32Array;
        parentIndices?: Int32Array;
        offscreenIndices?: Int32Array;
      };
    }).parts;

    const ids = parts?.ids ?? [];
    const opacities = parts?.opacities ?? new Float32Array(0);
    const count = parts?.count ?? ids.length ?? opacities.length ?? 0;

    return {
      count,
      ids,
      opacities,
      parentIndices:
        parts?.parentIndices ?? new Int32Array(count).fill(NoParentIndex),
      offscreenIndices:
        parts?.offscreenIndices ?? new Int32Array(count).fill(NoOffscreenIndex)
    };
  }

  private getCoreDrawables(): {
    count: number;
    ids: string[];
    constantFlags: Uint8Array;
    dynamicFlags: Uint8Array;
    textureIndices: Int32Array;
    indexCounts: Int32Array;
    vertexCounts: Int32Array;
    indices: Uint16Array[];
    vertexPositions: Float32Array[];
    vertexUvs: Float32Array[];
    opacities: Float32Array;
    renderOrders: Int32Array;
    masks: Int32Array[];
    maskCounts: Int32Array;
    parentPartIndices: Int32Array;
    blendModes: Uint16Array;
    multiplyColors: Float32Array;
    screenColors: Float32Array;
  } {
    const drawables = (this._model as Live2DCubismCore.Model & {
      drawables?: {
        count?: number;
        ids?: string[];
        constantFlags?: Uint8Array;
        dynamicFlags?: Uint8Array;
        textureIndices?: Int32Array;
        indexCounts?: Int32Array;
        vertexCounts?: Int32Array;
        indices?: Uint16Array[];
        vertexPositions?: Float32Array[];
        vertexUvs?: Float32Array[];
        opacities?: Float32Array;
        renderOrders?: Int32Array;
        masks?: Int32Array[];
        maskCounts?: Int32Array;
        parentPartIndices?: Int32Array;
        blendModes?: Uint16Array;
        multiplyColors?: Float32Array;
        screenColors?: Float32Array;
      };
    }).drawables;

    const ids = drawables?.ids ?? [];
    const count =
      drawables?.count ??
      ids.length ??
      drawables?.parentPartIndices?.length ??
      drawables?.constantFlags?.length ??
      drawables?.dynamicFlags?.length ??
      drawables?.maskCounts?.length ??
      0;

    return {
      count,
      ids,
      constantFlags: drawables?.constantFlags ?? new Uint8Array(count),
      dynamicFlags: drawables?.dynamicFlags ?? new Uint8Array(count),
      textureIndices: drawables?.textureIndices ?? new Int32Array(count),
      indexCounts: drawables?.indexCounts ?? new Int32Array(count),
      vertexCounts: drawables?.vertexCounts ?? new Int32Array(count),
      indices:
        drawables?.indices ??
        Array.from({ length: count }, () => new Uint16Array(0)),
      vertexPositions:
        drawables?.vertexPositions ??
        Array.from({ length: count }, () => new Float32Array(0)),
      vertexUvs:
        drawables?.vertexUvs ??
        Array.from({ length: count }, () => new Float32Array(0)),
      opacities: drawables?.opacities ?? new Float32Array(count),
      renderOrders:
        drawables?.renderOrders ??
        Int32Array.from(Array.from({ length: count }, (_, index) => index)),
      masks:
        drawables?.masks ?? Array.from({ length: count }, () => new Int32Array(0)),
      maskCounts: drawables?.maskCounts ?? new Int32Array(count),
      parentPartIndices:
        drawables?.parentPartIndices ?? new Int32Array(count).fill(NoParentIndex),
      blendModes: drawables?.blendModes ?? new Uint16Array(count),
      multiplyColors: drawables?.multiplyColors ?? new Float32Array(count * 4),
      screenColors: drawables?.screenColors ?? new Float32Array(count * 4)
    };
  }

  private getCoreOffscreens(): {
    count: number;
    ownerIndices: Int32Array;
    opacities: Float32Array;
    masks: Int32Array[];
    maskCounts: Int32Array;
    constantFlags: Uint8Array;
    blendModes: Uint16Array;
    multiplyColors: Float32Array;
    screenColors: Float32Array;
  } {
    const offscreens = (this._model as Live2DCubismCore.Model & {
      offscreens?: {
        count?: number;
        ownerIndices?: Int32Array;
        opacities?: Float32Array;
        masks?: Int32Array[];
        maskCounts?: Int32Array;
        constantFlags?: Uint8Array;
        blendModes?: Uint16Array;
        multiplyColors?: Float32Array;
        screenColors?: Float32Array;
      };
    }).offscreens;

    return {
      count: offscreens?.count ?? 0,
      ownerIndices: offscreens?.ownerIndices ?? new Int32Array(0),
      opacities: offscreens?.opacities ?? new Float32Array(0),
      masks: offscreens?.masks ?? [],
      maskCounts: offscreens?.maskCounts ?? new Int32Array(0),
      constantFlags: offscreens?.constantFlags ?? new Uint8Array(0),
      blendModes: offscreens?.blendModes ?? new Uint16Array(0),
      multiplyColors: offscreens?.multiplyColors ?? new Float32Array(0),
      screenColors: offscreens?.screenColors ?? new Float32Array(0)
    };
  }
  /**
   * モデルのパラメータの更新
   */
  public update(): void {
    // Update model
    this._model.update();

    this._model.drawables?.resetDynamicFlags?.();
  }

  /**
   * PixelsPerUnitを取得する
   * @return PixelsPerUnit
   */
  public getPixelsPerUnit(): number {
    if (this._model == null) {
      return 0.0;
    }

    return this._model.canvasinfo.PixelsPerUnit;
  }

  /**
   * キャンバスの幅を取得する
   */
  public getCanvasWidth(): number {
    if (this._model == null) {
      return 0.0;
    }

    return (
      this._model.canvasinfo.CanvasWidth / this._model.canvasinfo.PixelsPerUnit
    );
  }

  /**
   * キャンバスの高さを取得する
   */
  public getCanvasHeight(): number {
    if (this._model == null) {
      return 0.0;
    }

    return (
      this._model.canvasinfo.CanvasHeight / this._model.canvasinfo.PixelsPerUnit
    );
  }

  /**
   * パラメータを保存する
   */
  public saveParameters(): void {
    const parameterCount: number = this.getCoreParameters().count;
    const savedParameterCount: number = this._savedParameters.length;

    for (let i = 0; i < parameterCount; ++i) {
      if (i < savedParameterCount) {
        this._savedParameters[i] = this._parameterValues[i];
      } else {
        this._savedParameters.push(this._parameterValues[i]);
      }
    }
  }

  /**
   * 乗算色・スクリーン色管理クラスを取得する
   *
   * @return CubismModelMultiplyAndScreenColorのインスタンス
   */
  public getOverrideMultiplyAndScreenColor(): CubismModelMultiplyAndScreenColor {
    return this._overrideMultiplyAndScreenColor;
  }

  /**
   * Checks whether parameter repetition is performed for the entire model.
   *
   * @return true if parameter repetition is performed for the entire model; otherwise returns false.
   */
  public getOverrideFlagForModelParameterRepeat(): boolean {
    return this._isOverriddenParameterRepeat;
  }

  /**
   * Sets whether parameter repetition is performed for the entire model.
   * Use true to perform parameter repetition for the entire model, or false to not perform it.
   */
  public setOverrideFlagForModelParameterRepeat(isRepeat: boolean): void {
    this._isOverriddenParameterRepeat = isRepeat;
  }

  /**
   * Returns the flag indicating whether to override the parameter repeat.
   *
   * @param parameterIndex Parameter index
   *
   * @return true if the parameter repeat is overridden, false otherwise.
   */
  public getOverrideFlagForParameterRepeat(parameterIndex: number): boolean {
    return this._userParameterRepeatDataList[parameterIndex].isOverridden;
  }

  /**
   * Sets the flag indicating whether to override the parameter repeat.
   *
   * @param parameterIndex Parameter index
   * @param value true if it is to be overridden; otherwise, false.
   */
  public setOverrideFlagForParameterRepeat(
    parameterIndex: number,
    value: boolean
  ): void {
    this._userParameterRepeatDataList[parameterIndex].isOverridden = value;
  }

  /**
   * Returns the repeat flag.
   *
   * @param parameterIndex Parameter index
   *
   * @return true if repeating, false otherwise.
   */
  public getRepeatFlagForParameterRepeat(parameterIndex: number): boolean {
    return this._userParameterRepeatDataList[parameterIndex]
      .isParameterRepeated;
  }

  /**
   * Sets the repeat flag.
   *
   * @param parameterIndex Parameter index
   * @param value true to enable repeating, false otherwise.
   */
  public setRepeatFlagForParameterRepeat(
    parameterIndex: number,
    value: boolean
  ): void {
    this._userParameterRepeatDataList[parameterIndex].isParameterRepeated =
      value;
  }

  /**
   * Drawableのカリング情報を取得する。
   *
   * @param   drawableIndex   Drawableのインデックス
   *
   * @return  Drawableのカリング情報
   */
  public getDrawableCulling(drawableIndex: number): boolean {
    if (
      this.getOverrideFlagForModelCullings() ||
      this.getOverrideFlagForDrawableCullings(drawableIndex)
    ) {
      return this._userDrawableCullings[drawableIndex].isCulling;
    }

    const constantFlags = this.getCoreDrawables().constantFlags;
    return !Live2DCubismCore.Utils.hasIsDoubleSidedBit(
      constantFlags[drawableIndex]
    );
  }

  /**
   * Drawableのカリング情報を設定する。
   *
   * @param drawableIndex Drawableのインデックス
   * @param isCulling カリング情報
   */
  public setDrawableCulling(drawableIndex: number, isCulling: boolean): void {
    this._userDrawableCullings[drawableIndex].isCulling = isCulling;
  }

  /**
   * Offscreenのカリング情報を取得する。
   *
   * @param   offscreenIndex   Offscreenのインデックス
   *
   * @return  Offscreenのカリング情報
   */
  public getOffscreenCulling(offscreenIndex: number): boolean {
    if (
      this.getOverrideFlagForModelCullings() ||
      this.getOverrideFlagForOffscreenCullings(offscreenIndex)
    ) {
      return this._userOffscreenCullings[offscreenIndex].isCulling;
    }

    const constantFlags = this.getCoreOffscreens().constantFlags;
    return !Live2DCubismCore.Utils.hasIsDoubleSidedBit(
      constantFlags[offscreenIndex]
    );
  }

  /**
   * Offscreenのカリング設定を設定する。
   *
   * @param offscreenIndex Offscreenのインデックス
   * @param isCulling カリング情報
   */
  public setOffscreenCulling(offscreenIndex: number, isCulling: boolean): void {
    this._userOffscreenCullings[offscreenIndex].isCulling = isCulling;
  }

  /**
   * SDKからモデル全体のカリング設定を上書きするか。
   *
   * @return  true    ->  SDK上のカリング設定を使用
   *          false   ->  モデルのカリング設定を使用
   */
  public getOverrideFlagForModelCullings(): boolean {
    return this._isOverriddenCullings;
  }

  /**
   * SDKからモデル全体のカリング設定を上書きするかを設定する。
   *
   * @param isOverriddenCullings SDK上のカリング設定を使うならtrue、モデルのカリング設定を使うならfalse
   */
  public setOverrideFlagForModelCullings(isOverriddenCullings: boolean): void {
    this._isOverriddenCullings = isOverriddenCullings;
  }

  /**
   *
   * @param drawableIndex Drawableのインデックス
   * @return  true    ->  SDK上のカリング設定を使用
   *          false   ->  モデルのカリング設定を使用
   */
  public getOverrideFlagForDrawableCullings(drawableIndex: number): boolean {
    return this._userDrawableCullings[drawableIndex].isOverridden;
  }

  /**
   * @param offscreenIndex Offscreenのインデックス
   * @return  true    ->  SDK上のカリング設定を使用
   *          false   ->  モデルのカリング設定を使用
   */
  public getOverrideFlagForOffscreenCullings(offscreenIndex: number): boolean {
    return this._userOffscreenCullings[offscreenIndex].isOverridden;
  }

  /**
   *
   * @param drawableIndex Drawableのインデックス
   * @param isOverriddenCullings SDK上のカリング設定を使うならtrue、モデルのカリング設定を使うならfalse
   */
  public setOverrideFlagForDrawableCullings(
    drawableIndex: number,
    isOverriddenCullings: boolean
  ): void {
    this._userDrawableCullings[drawableIndex].isOverridden =
      isOverriddenCullings;
  }

  /**
   * モデルの不透明度を取得する
   *
   * @return 不透明度の値
   */
  public getModelOapcity(): number {
    return this._modelOpacity;
  }

  /**
   * モデルの不透明度を設定する
   *
   * @param value 不透明度の値
   */
  public setModelOapcity(value: number) {
    this._modelOpacity = value;
  }

  /**
   * モデルを取得
   */
  public getModel(): Live2DCubismCore.Model {
    return this._model;
  }

  /**
   * パーツのインデックスを取得
   * @param partId パーツのID
   * @return パーツのインデックス
   */
  public getPartIndex(partId: CubismIdHandle): number {
    let partIndex: number;
    const partCount: number = this.getCoreParts().count;

    for (partIndex = 0; partIndex < partCount; ++partIndex) {
      if (partId == this._partIds[partIndex]) {
        return partIndex;
      }
    }

    // モデルに存在していない場合、非存在パーツIDリスト内にあるかを検索し、そのインデックスを返す
    if (this._notExistPartId.has(partId)) {
      return this._notExistPartId.get(partId);
    }

    // 非存在パーツIDリストにない場合、新しく要素を追加する
    partIndex = partCount + this._notExistPartId.size;
    this._notExistPartId.set(partId, partIndex);
    this._notExistPartOpacities.set(partIndex, null);

    return partIndex;
  }

  /**
   * パーツのIDを取得する。
   *
   * @param partIndex 取得するパーツのインデックス
   * @return パーツのID
   */
  public getPartId(partIndex: number): CubismIdHandle {
    const partId = this.getCoreParts().ids[partIndex];
    return CubismFramework.getIdManager().getId(partId);
  }

  /**
   * パーツの個数の取得
   * @return パーツの個数
   */
  public getPartCount(): number {
    const partCount: number = this.getCoreParts().count;
    return partCount;
  }

  /**
   * パーツのオフスクリーンインデックスの取得
   * @param partIndex パーツのインデックス
   * @return オフスクリーンインデックスのリスト
   */
  public getPartOffscreenIndices(): Int32Array {
    const offscreenIndices = this.getCoreParts().offscreenIndices;
    return offscreenIndices;
  }

  /**
   * パーツの親パーツインデックスのリストを取得
   *
   * @return パーツの親パーツインデックスのリスト
   */
  public getPartParentPartIndices(): Int32Array {
    const parentIndices = this.getCoreParts().parentIndices;
    return parentIndices;
  }

  /**
   * パーツの不透明度の設定(Index)
   * @param partIndex パーツのインデックス
   * @param opacity 不透明度
   */
  public setPartOpacityByIndex(partIndex: number, opacity: number): void {
    if (this._notExistPartOpacities.has(partIndex)) {
      this._notExistPartOpacities.set(partIndex, opacity);
      return;
    }

    // インデックスの範囲内検知
    CSM_ASSERT(0 <= partIndex && partIndex < this.getPartCount());

    this._partOpacities[partIndex] = opacity;
  }

  /**
   * パーツの不透明度の設定(Id)
   * @param partId パーツのID
   * @param opacity パーツの不透明度
   */
  public setPartOpacityById(partId: CubismIdHandle, opacity: number): void {
    // 高速化のためにPartIndexを取得できる機構になっているが、外部からの設定の時は呼び出し頻度が低いため不要
    const index: number = this.getPartIndex(partId);

    if (index < 0) {
      return; // パーツがないのでスキップ
    }

    this.setPartOpacityByIndex(index, opacity);
  }

  /**
   * パーツの不透明度の取得(index)
   * @param partIndex パーツのインデックス
   * @return パーツの不透明度
   */
  public getPartOpacityByIndex(partIndex: number): number {
    if (this._notExistPartOpacities.has(partIndex)) {
      // モデルに存在しないパーツIDの場合、非存在パーツリストから不透明度を返す。
      return this._notExistPartOpacities.get(partIndex);
    }

    // インデックスの範囲内検知
    CSM_ASSERT(0 <= partIndex && partIndex < this.getPartCount());

    return this._partOpacities[partIndex];
  }

  /**
   * パーツの不透明度の取得(id)
   * @param partId パーツのＩｄ
   * @return パーツの不透明度
   */
  public getPartOpacityById(partId: CubismIdHandle): number {
    // 高速化のためにPartIndexを取得できる機構になっているが、外部からの設定の時は呼び出し頻度が低いため不要
    const index: number = this.getPartIndex(partId);

    if (index < 0) {
      return 0; // パーツが無いのでスキップ
    }

    return this.getPartOpacityByIndex(index);
  }

  /**
   * パラメータのインデックスの取得
   * @param パラメータID
   * @return パラメータのインデックス
   */
  public getParameterIndex(parameterId: CubismIdHandle): number {
    let parameterIndex: number;
    const idCount: number = this.getCoreParameters().count;

    for (parameterIndex = 0; parameterIndex < idCount; ++parameterIndex) {
      if (parameterId != this._parameterIds[parameterIndex]) {
        continue;
      }

      return parameterIndex;
    }

    // モデルに存在していない場合、非存在パラメータIDリスト内を検索し、そのインデックスを返す
    if (this._notExistParameterId.has(parameterId)) {
      return this._notExistParameterId.get(parameterId);
    }

    // 非存在パラメータIDリストにない場合新しく要素を追加する
    parameterIndex =
      this.getCoreParameters().count + this._notExistParameterId.size;

    this._notExistParameterId.set(parameterId, parameterIndex);
    this._notExistParameterValues.set(parameterIndex, null);

    return parameterIndex;
  }

  /**
   * パラメータの個数の取得
   * @return パラメータの個数
   */
  public getParameterCount(): number {
    return this.getCoreParameters().count;
  }

  /**
   * パラメータの種類の取得
   * @param parameterIndex パラメータのインデックス
   * @return csmParameterType_Normal -> 通常のパラメータ
   *          csmParameterType_BlendShape -> ブレンドシェイプパラメータ
   */
  public getParameterType(
    parameterIndex: number
  ): Live2DCubismCore.csmParameterType {
    return this.getCoreParameters().types[parameterIndex];
  }

  /**
   * パラメータの最大値の取得
   * @param parameterIndex パラメータのインデックス
   * @return パラメータの最大値
   */
  public getParameterMaximumValue(parameterIndex: number): number {
    return this.getCoreParameters().maximumValues[parameterIndex];
  }

  /**
   * パラメータの最小値の取得
   * @param parameterIndex パラメータのインデックス
   * @return パラメータの最小値
   */
  public getParameterMinimumValue(parameterIndex: number): number {
    return this.getCoreParameters().minimumValues[parameterIndex];
  }

  /**
   * パラメータのデフォルト値の取得
   * @param parameterIndex パラメータのインデックス
   * @return パラメータのデフォルト値
   */
  public getParameterDefaultValue(parameterIndex: number): number {
    return this.getCoreParameters().defaultValues[parameterIndex];
  }

  /**
   * 指定したパラメータindexのIDを取得
   *
   * @param parameterIndex パラメータのインデックス
   * @return パラメータID
   */
  public getParameterId(parameterIndex: number): CubismIdHandle {
    return CubismFramework.getIdManager().getId(
      this.getCoreParameters().ids[parameterIndex]
    );
  }

  /**
   * パラメータの値の取得
   * @param parameterIndex    パラメータのインデックス
   * @return パラメータの値
   */
  public getParameterValueByIndex(parameterIndex: number): number {
    if (this._notExistParameterValues.has(parameterIndex)) {
      return this._notExistParameterValues.get(parameterIndex);
    }

    // インデックスの範囲内検知
    CSM_ASSERT(
      0 <= parameterIndex && parameterIndex < this.getParameterCount()
    );

    return this._parameterValues[parameterIndex];
  }

  /**
   * パラメータの値の取得
   * @param parameterId    パラメータのID
   * @return パラメータの値
   */
  public getParameterValueById(parameterId: CubismIdHandle): number {
    // 高速化のためにparameterIndexを取得できる機構になっているが、外部からの設定の時は呼び出し頻度が低いため不要
    const parameterIndex: number = this.getParameterIndex(parameterId);
    return this.getParameterValueByIndex(parameterIndex);
  }

  /**
   * パラメータの値の設定
   * @param parameterIndex パラメータのインデックス
   * @param value パラメータの値
   * @param weight 重み
   */
  public setParameterValueByIndex(
    parameterIndex: number,
    value: number,
    weight = 1.0
  ): void {
    if (this._notExistParameterValues.has(parameterIndex)) {
      this._notExistParameterValues.set(
        parameterIndex,
        weight == 1
          ? value
          : this._notExistParameterValues.get(parameterIndex) * (1 - weight) +
              value * weight
      );

      return;
    }

    // インデックスの範囲内検知
    CSM_ASSERT(
      0 <= parameterIndex && parameterIndex < this.getParameterCount()
    );

    if (this.isRepeat(parameterIndex)) {
      value = this.getParameterRepeatValue(parameterIndex, value);
    } else {
      value = this.getParameterClampValue(parameterIndex, value);
    }

    this._parameterValues[parameterIndex] =
      weight == 1
        ? value
        : (this._parameterValues[parameterIndex] =
            this._parameterValues[parameterIndex] * (1 - weight) +
            value * weight);
  }

  /**
   * パラメータの値の設定
   * @param parameterId パラメータのID
   * @param value パラメータの値
   * @param weight 重み
   */
  public setParameterValueById(
    parameterId: CubismIdHandle,
    value: number,
    weight = 1.0
  ): void {
    const index: number = this.getParameterIndex(parameterId);
    this.setParameterValueByIndex(index, value, weight);
  }

  /**
   * パラメータの値の加算(index)
   * @param parameterIndex パラメータインデックス
   * @param value 加算する値
   * @param weight 重み
   */
  public addParameterValueByIndex(
    parameterIndex: number,
    value: number,
    weight = 1.0
  ): void {
    this.setParameterValueByIndex(
      parameterIndex,
      this.getParameterValueByIndex(parameterIndex) + value * weight
    );
  }

  /**
   * パラメータの値の加算(id)
   * @param parameterId パラメータＩＤ
   * @param value 加算する値
   * @param weight 重み
   */
  public addParameterValueById(
    parameterId: any,
    value: number,
    weight = 1.0
  ): void {
    const index: number = this.getParameterIndex(parameterId);
    this.addParameterValueByIndex(index, value, weight);
  }

  /**
   * Gets whether the parameter has the repeat setting.
   *
   * @param parameterIndex Parameter index
   *
   * @return true if it is set, otherwise returns false.
   */
  public isRepeat(parameterIndex: number): boolean {
    if (this._notExistParameterValues.has(parameterIndex)) {
      return false;
    }

    // In-index range detection
    CSM_ASSERT(
      0 <= parameterIndex && parameterIndex < this.getParameterCount()
    );

    let isRepeat: boolean;

    // Determines whether to perform parameter repeat processing
    if (
      this._isOverriddenParameterRepeat ||
      this._userParameterRepeatDataList[parameterIndex].isOverridden
    ) {
      // Use repeat information set on the SDK side
      isRepeat =
        this._userParameterRepeatDataList[parameterIndex].isParameterRepeated;
    } else {
      // Use repeat information set in Editor
      isRepeat = this.getCoreParameters().repeats[parameterIndex] != 0;
    }

    return isRepeat;
  }

  /**
   * Returns the calculated result ensuring the value falls within the parameter's range.
   *
   * @param parameterIndex Parameter index
   * @param value Parameter value
   *
   * @return a value that falls within the parameter’s range. If the parameter does not exist, returns it as is.
   */
  public getParameterRepeatValue(
    parameterIndex: number,
    value: number
  ): number {
    if (this._notExistParameterValues.has(parameterIndex)) {
      return value;
    }

    // In-index range detection
    CSM_ASSERT(
      0 <= parameterIndex && parameterIndex < this.getParameterCount()
    );

    const maxValue: number =
      this.getCoreParameters().maximumValues[parameterIndex];
    const minValue: number =
      this.getCoreParameters().minimumValues[parameterIndex];
    const valueSize: number = maxValue - minValue;

    if (maxValue < value) {
      const overValue: number = CubismMath.mod(value - maxValue, valueSize);
      if (!Number.isNaN(overValue)) {
        value = minValue + overValue;
      } else {
        value = maxValue;
      }
    }
    if (value < minValue) {
      const overValue: number = CubismMath.mod(minValue - value, valueSize);
      if (!Number.isNaN(overValue)) {
        value = maxValue - overValue;
      } else {
        value = minValue;
      }
    }

    return value;
  }

  /**
   * Returns the result of clamping the value to ensure it falls within the parameter's range.
   *
   * @param parameterIndex Parameter index
   * @param value Parameter value
   *
   * @return the clamped value. If the parameter does not exist, returns it as is.
   */
  public getParameterClampValue(parameterIndex: number, value: number): number {
    if (this._notExistParameterValues.has(parameterIndex)) {
      return value;
    }

    // In-index range detection
    CSM_ASSERT(
      0 <= parameterIndex && parameterIndex < this.getParameterCount()
    );

    const maxValue: number =
      this.getCoreParameters().maximumValues[parameterIndex];
    const minValue: number =
      this.getCoreParameters().minimumValues[parameterIndex];

    return CubismMath.clamp(value, minValue, maxValue);
  }

  /**
   * Returns the repeat of the parameter.
   *
   * @param parameterIndex Parameter index
   *
   * @return the raw data parameter repeat from the Cubism Core.
   */
  public getParameterRepeats(parameterIndex: number): boolean {
    return this.getCoreParameters().repeats[parameterIndex] != 0;
  }

  /**
   * パラメータの値の乗算
   * @param parameterId パラメータのID
   * @param value 乗算する値
   * @param weight 重み
   */
  public multiplyParameterValueById(
    parameterId: CubismIdHandle,
    value: number,
    weight = 1.0
  ): void {
    const index: number = this.getParameterIndex(parameterId);
    this.multiplyParameterValueByIndex(index, value, weight);
  }

  /**
   * パラメータの値の乗算
   * @param parameterIndex パラメータのインデックス
   * @param value 乗算する値
   * @param weight 重み
   */
  public multiplyParameterValueByIndex(
    parameterIndex: number,
    value: number,
    weight = 1.0
  ): void {
    this.setParameterValueByIndex(
      parameterIndex,
      this.getParameterValueByIndex(parameterIndex) *
        (1.0 + (value - 1.0) * weight)
    );
  }

  /**
   * Drawableのインデックスの取得
   * @param drawableId DrawableのID
   * @return Drawableのインデックス
   */
  public getDrawableIndex(drawableId: CubismIdHandle): number {
    const drawableCount = this.getCoreDrawables().count;

    for (
      let drawableIndex = 0;
      drawableIndex < drawableCount;
      ++drawableIndex
    ) {
      if (this._drawableIds[drawableIndex] == drawableId) {
        return drawableIndex;
      }
    }

    return -1;
  }

  /**
   * Drawableの個数の取得
   * @return drawableの個数
   */
  public getDrawableCount(): number {
    const drawableCount = this.getCoreDrawables().count;
    return drawableCount;
  }

  /**
   * DrawableのIDを取得する
   * @param drawableIndex Drawableのインデックス
   * @return drawableのID
   */
  public getDrawableId(drawableIndex: number): CubismIdHandle {
    const parameterIds: string[] = this.getCoreDrawables().ids;
    return CubismFramework.getIdManager().getId(parameterIds[drawableIndex]);
  }

  /**
   * Drawableの描画順リストの取得
   * @return Drawableの描画順リスト
   */
  public getRenderOrders(): Int32Array {
    const model = this._model as
      | (Live2DCubismCore.Model & {
          getRenderOrders?: () => Int32Array;
          getDrawableRenderOrders?: () => Int32Array;
        })
      | null;

    if (!model) {
      return new Int32Array(0);
    }

    const drawableRenderOrders = this.getCoreDrawables().renderOrders;
    if (drawableRenderOrders.length > 0) {
      return drawableRenderOrders;
    }

    if (typeof model.getDrawableRenderOrders === 'function') {
      return model.getDrawableRenderOrders();
    }

    if (typeof model.getRenderOrders === 'function') {
      return model.getRenderOrders();
    }

    const drawableCount = this.getDrawableCount();
    const fallback = new Int32Array(drawableCount);
    for (let i = 0; i < drawableCount; i++) {
      fallback[i] = i;
    }
    return fallback;
  }

  /**
   * Drawableのテクスチャインデックスの取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableのテクスチャインデックス
   */
  public getDrawableTextureIndex(drawableIndex: number): number {
    const textureIndices: Int32Array = this.getCoreDrawables().textureIndices;
    return textureIndices[drawableIndex];
  }

  /**
   * DrawableのVertexPositionsの変化情報の取得
   *
   * 直近のCubismModel.update関数でDrawableの頂点情報が変化したかを取得する。
   *
   * @param   drawableIndex   Drawableのインデックス
   * @return  true    Drawableの頂点情報が直近のCubismModel.update関数で変化した
   *          false   Drawableの頂点情報が直近のCubismModel.update関数で変化していない
   */
  public getDrawableDynamicFlagVertexPositionsDidChange(
    drawableIndex: number
  ): boolean {
    const dynamicFlags: Uint8Array = this.getCoreDrawables().dynamicFlags;
    return Live2DCubismCore.Utils.hasVertexPositionsDidChangeBit(
      dynamicFlags[drawableIndex]
    );
  }

  /**
   * Drawableの頂点インデックスの個数の取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの頂点インデックスの個数
   */
  public getDrawableVertexIndexCount(drawableIndex: number): number {
    const indexCounts: Int32Array = this.getCoreDrawables().indexCounts;
    return indexCounts[drawableIndex];
  }

  /**
   * Drawableの頂点の個数の取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの頂点の個数
   */
  public getDrawableVertexCount(drawableIndex: number): number {
    const vertexCounts: Int32Array = this.getCoreDrawables().vertexCounts;
    return vertexCounts[drawableIndex];
  }

  /**
   * Drawableの頂点リストの取得
   * @param drawableIndex drawableのインデックス
   * @return drawableの頂点リスト
   */
  public getDrawableVertices(drawableIndex: number): Float32Array {
    return this.getDrawableVertexPositions(drawableIndex);
  }

  /**
   * Drawableの頂点インデックスリストの取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの頂点インデックスリスト
   */
  public getDrawableVertexIndices(drawableIndex: number): Uint16Array {
    const indicesArray: Uint16Array[] = this.getCoreDrawables().indices;
    return indicesArray[drawableIndex];
  }

  /**
   * Drawableの頂点リストの取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの頂点リスト
   */
  public getDrawableVertexPositions(drawableIndex: number): Float32Array {
    const verticesArray: Float32Array[] = this.getCoreDrawables().vertexPositions;
    return verticesArray[drawableIndex];
  }

  /**
   * Drawableの頂点のUVリストの取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの頂点UVリスト
   */
  public getDrawableVertexUvs(drawableIndex: number): Float32Array {
    const uvsArray: Float32Array[] = this.getCoreDrawables().vertexUvs;
    return uvsArray[drawableIndex];
  }

  /**
   * Drawableの不透明度の取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの不透明度
   */
  public getDrawableOpacity(drawableIndex: number): number {
    const opacities: Float32Array = this.getCoreDrawables().opacities;
    return opacities[drawableIndex];
  }

  /**
   * Drawableの乗算色の取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの乗算色(RGBA)
   * スクリーン色はRGBAで取得されるが、Aは必ず0
   */
  public getDrawableMultiplyColor(drawableIndex: number): CubismTextureColor {
    if (this._drawableMultiplyColors == null) {
      this._drawableMultiplyColors = new Array<CubismTextureColor>(
        this.getCoreDrawables().count
      );
      this._drawableMultiplyColors.fill(new CubismTextureColor());
    }
    const multiplyColors: Float32Array = this.getCoreDrawables().multiplyColors;

    const index = drawableIndex * 4;
    this._drawableMultiplyColors[drawableIndex].r = multiplyColors[index];
    this._drawableMultiplyColors[drawableIndex].g = multiplyColors[index + 1];
    this._drawableMultiplyColors[drawableIndex].b = multiplyColors[index + 2];
    this._drawableMultiplyColors[drawableIndex].a = multiplyColors[index + 3];
    return this._drawableMultiplyColors[drawableIndex];
  }

  /**
   * Drawableのスクリーン色の取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableのスクリーン色(RGBA)
   * スクリーン色はRGBAで取得されるが、Aは必ず0
   */
  public getDrawableScreenColor(drawableIndex: number): CubismTextureColor {
    if (this._drawableScreenColors == null) {
      this._drawableScreenColors = new Array<CubismTextureColor>(
        this.getCoreDrawables().count
      );
      this._drawableScreenColors.fill(new CubismTextureColor());
    }
    const screenColors: Float32Array = this.getCoreDrawables().screenColors;

    const index = drawableIndex * 4;
    this._drawableScreenColors[drawableIndex].r = screenColors[index];
    this._drawableScreenColors[drawableIndex].g = screenColors[index + 1];
    this._drawableScreenColors[drawableIndex].b = screenColors[index + 2];
    this._drawableScreenColors[drawableIndex].a = screenColors[index + 3];
    return this._drawableScreenColors[drawableIndex];
  }

  /**
   * Offscreenの乗算色の取得
   * @param offscreenIndex Offscreenのインデックス
   * @return Offscreenの乗算色(RGBA)
   * スクリーン色はRGBAで取得されるが、Aは必ず0
   */
  public getOffscreenMultiplyColor(offscreenIndex: number): CubismTextureColor {
    if (this._offscreenMultiplyColors == null) {
      this._offscreenMultiplyColors = new Array<CubismTextureColor>(
        this.getCoreOffscreens().count
      );
      this._offscreenMultiplyColors.fill(new CubismTextureColor());
    }
    const multiplyColors: Float32Array = this.getCoreOffscreens().multiplyColors;

    const index = offscreenIndex * 4;
    this._offscreenMultiplyColors[offscreenIndex].r = multiplyColors[index];
    this._offscreenMultiplyColors[offscreenIndex].g = multiplyColors[index + 1];
    this._offscreenMultiplyColors[offscreenIndex].b = multiplyColors[index + 2];
    this._offscreenMultiplyColors[offscreenIndex].a = multiplyColors[index + 3];
    return this._offscreenMultiplyColors[offscreenIndex];
  }

  /**
   * Offscreenのスクリーン色の取得
   * @param offscreenIndex Offscreenのインデックス
   * @return Offscreenのスクリーン色(RGBA)
   * スクリーン色はRGBAで取得されるが、Aは必ず0
   */
  public getOffscreenScreenColor(offscreenIndex: number): CubismTextureColor {
    if (this._offscreenScreenColors == null) {
      this._offscreenScreenColors = new Array<CubismTextureColor>(
        this.getCoreOffscreens().count
      );
      this._offscreenScreenColors.fill(new CubismTextureColor());
    }
    const screenColors: Float32Array = this.getCoreOffscreens().screenColors;

    const index = offscreenIndex * 4;
    this._offscreenScreenColors[offscreenIndex].r = screenColors[index];
    this._offscreenScreenColors[offscreenIndex].g = screenColors[index + 1];
    this._offscreenScreenColors[offscreenIndex].b = screenColors[index + 2];
    this._offscreenScreenColors[offscreenIndex].a = screenColors[index + 3];
    return this._offscreenScreenColors[offscreenIndex];
  }

  /**
   * Drawableの親パーツのインデックスの取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableの親パーツのインデックス
   */
  public getDrawableParentPartIndex(drawableIndex: number): number {
    return this.getCoreDrawables().parentPartIndices[drawableIndex];
  }

  /**
   * Drawableのブレンドモードを取得
   * @param drawableIndex Drawableのインデックス
   * @return drawableのブレンドモード
   */
  public getDrawableBlendMode(drawableIndex: number): CubismBlendMode {
    const constantFlags = this.getCoreDrawables().constantFlags;

    return Live2DCubismCore.Utils.hasBlendAdditiveBit(
      constantFlags[drawableIndex]
    )
      ? CubismBlendMode.CubismBlendMode_Additive
      : Live2DCubismCore.Utils.hasBlendMultiplicativeBit(
            constantFlags[drawableIndex]
          )
        ? CubismBlendMode.CubismBlendMode_Multiplicative
        : CubismBlendMode.CubismBlendMode_Normal;
  }

  /**
   * Drawableのカラーブレンドの取得(Cubism 5.3 以降)
   *
   * @param drawableIndex Drawableのインデックス
   * @return Drawableのカラーブレンド
   */
  public getDrawableColorBlend(drawableIndex: number): CubismColorBlend {
    // キャッシュ
    if (
      this._drawableColorBlends[drawableIndex] ==
      CubismColorBlend.ColorBlend_None
    ) {
      this._drawableColorBlends[drawableIndex] =
        this.getCoreDrawables().blendModes[drawableIndex] & 0xff;
    }
    return this._drawableColorBlends[drawableIndex];
  }

  /**
   * Drawableのアルファブレンドの取得(Cubism 5.3 以降)
   *
   * @param drawableIndex Drawableのインデックス
   * @return Drawableのアルファブレンド
   */
  public getDrawableAlphaBlend(drawableIndex: number): CubismAlphaBlend {
    // キャッシュ
    if (
      this._drawableAlphaBlends[drawableIndex] ==
      CubismAlphaBlend.AlphaBlend_None
    ) {
      this._drawableAlphaBlends[drawableIndex] =
        (this.getCoreDrawables().blendModes[drawableIndex] >> 8) & 0xff;
    }
    return this._drawableAlphaBlends[drawableIndex];
  }

  /**
   * Drawableのマスクの反転使用の取得
   *
   * Drawableのマスク使用時の反転設定を取得する。
   * マスクを使用しない場合は無視される。
   *
   * @param drawableIndex Drawableのインデックス
   * @return Drawableの反転設定
   */
  public getDrawableInvertedMaskBit(drawableIndex: number): boolean {
    const constantFlags: Uint8Array = this.getCoreDrawables().constantFlags;

    return Live2DCubismCore.Utils.hasIsInvertedMaskBit(
      constantFlags[drawableIndex]
    );
  }

  /**
   * Drawableのクリッピングマスクリストの取得
   * @return Drawableのクリッピングマスクリスト
   */
  public getDrawableMasks(): Int32Array[] {
    const masks: Int32Array[] = this.getCoreDrawables().masks;
    return masks;
  }

  /**
   * Drawableのクリッピングマスクの個数リストの取得
   * @return Drawableのクリッピングマスクの個数リスト
   */
  public getDrawableMaskCounts(): Int32Array {
    const maskCounts: Int32Array = this.getCoreDrawables().maskCounts;
    return maskCounts;
  }

  /**
   * クリッピングマスクの使用状態
   *
   * @return true クリッピングマスクを使用している
   * @return false クリッピングマスクを使用していない
   */
  public isUsingMasking(): boolean {
    const drawables = this.getCoreDrawables();
    for (let d = 0; d < drawables.count; ++d) {
      if (drawables.maskCounts[d] <= 0) {
        continue;
      }
      return true;
    }
    return false;
  }

  /**
   * Offscreenでクリッピングマスクを使用しているかどうかを取得
   *
   * @return true クリッピングマスクをオフスクリーンで使用している
   */
  public isUsingMaskingForOffscreen(): boolean {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return false;
    }

    for (let d = 0; d < this.getOffscreenCount(); ++d) {
      if (this.getCoreOffscreens().maskCounts[d] <= 0) {
        continue;
      }
      return true;
    }
    return false;
  }

  /**
   * Drawableの表示情報を取得する
   *
   * @param drawableIndex Drawableのインデックス
   * @return true Drawableが表示
   * @return false Drawableが非表示
   */
  public getDrawableDynamicFlagIsVisible(drawableIndex: number): boolean {
    const dynamicFlags: Uint8Array = this.getCoreDrawables().dynamicFlags;
    return Live2DCubismCore.Utils.hasIsVisibleBit(dynamicFlags[drawableIndex]);
  }

  /**
   * DrawableのDrawOrderの変化情報の取得
   *
   * 直近のCubismModel.update関数でdrawableのdrawOrderが変化したかを取得する。
   * drawOrderはartMesh上で指定する0から1000の情報
   * @param drawableIndex drawableのインデックス
   * @return true drawableの不透明度が直近のCubismModel.update関数で変化した
   * @return false drawableの不透明度が直近のCubismModel.update関数で変化している
   */
  public getDrawableDynamicFlagVisibilityDidChange(
    drawableIndex: number
  ): boolean {
    const dynamicFlags: Uint8Array = this.getCoreDrawables().dynamicFlags;
    return Live2DCubismCore.Utils.hasVisibilityDidChangeBit(
      dynamicFlags[drawableIndex]
    );
  }

  /**
   * Drawableの不透明度の変化情報の取得
   *
   * 直近のCubismModel.update関数でdrawableの不透明度が変化したかを取得する。
   *
   * @param drawableIndex drawableのインデックス
   * @return true Drawableの不透明度が直近のCubismModel.update関数で変化した
   * @return false Drawableの不透明度が直近のCubismModel.update関数で変化してない
   */
  public getDrawableDynamicFlagOpacityDidChange(
    drawableIndex: number
  ): boolean {
    const dynamicFlags: Uint8Array = this.getCoreDrawables().dynamicFlags;
    return Live2DCubismCore.Utils.hasOpacityDidChangeBit(
      dynamicFlags[drawableIndex]
    );
  }

  /**
   * Drawableの描画順序の変化情報の取得
   *
   * 直近のCubismModel.update関数でDrawableの描画の順序が変化したかを取得する。
   *
   * @param drawableIndex Drawableのインデックス
   * @return true Drawableの描画の順序が直近のCubismModel.update関数で変化した
   * @return false Drawableの描画の順序が直近のCubismModel.update関数で変化してない
   */
  public getDrawableDynamicFlagRenderOrderDidChange(
    drawableIndex: number
  ): boolean {
    const dynamicFlags: Uint8Array = this.getCoreDrawables().dynamicFlags;
    return Live2DCubismCore.Utils.hasRenderOrderDidChangeBit(
      dynamicFlags[drawableIndex]
    );
  }

  /**
   * Drawableの乗算色・スクリーン色の変化情報の取得
   *
   * 直近のCubismModel.update関数でDrawableの乗算色・スクリーン色が変化したかを取得する。
   *
   * @param drawableIndex Drawableのインデックス
   * @return true Drawableの乗算色・スクリーン色が直近のCubismModel.update関数で変化した
   * @return false Drawableの乗算色・スクリーン色が直近のCubismModel.update関数で変化してない
   */
  public getDrawableDynamicFlagBlendColorDidChange(
    drawableIndex: number
  ): boolean {
    const dynamicFlags: Uint8Array = this.getCoreDrawables().dynamicFlags;
    return Live2DCubismCore.Utils.hasBlendColorDidChangeBit(
      dynamicFlags[drawableIndex]
    );
  }

  /**
   * オフスクリーンの個数を取得する
   * @return オフスクリーンの個数
   */
  public getOffscreenCount(): number {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return 0;
    }

    return this.getCoreOffscreens().count;
  }

  /**
   * Offscreenのカラーブレンドの取得(Cubism 5.3 以降)
   *
   * @param offscreenIndex Offscreenのインデックス
   * @return Offscreenのカラーブレンド
   */
  public getOffscreenColorBlend(offscreenIndex: number): CubismColorBlend {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return CubismColorBlend.ColorBlend_None;
    }

    // キャッシュ
    if (
      this._offscreenColorBlends[offscreenIndex] ==
      CubismColorBlend.ColorBlend_None
    ) {
      this._offscreenColorBlends[offscreenIndex] =
        this.getCoreOffscreens().blendModes[offscreenIndex] & 0xff;
    }
    return this._offscreenColorBlends[offscreenIndex];
  }

  /**
   * Offscreenのアルファブレンドの取得(Cubism 5.3 以降)
   *
   * @param offscreenIndex Offscreenのインデックス
   * @return Offscreenのアルファブレンド
   */
  public getOffscreenAlphaBlend(offscreenIndex: number): CubismAlphaBlend {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return CubismAlphaBlend.AlphaBlend_None;
    }

    // キャッシュ
    if (
      this._offscreenAlphaBlends[offscreenIndex] ==
      CubismAlphaBlend.AlphaBlend_None
    ) {
      this._offscreenAlphaBlends[offscreenIndex] =
        (this.getCoreOffscreens().blendModes[offscreenIndex] >> 8) & 0xff;
    }
    return this._offscreenAlphaBlends[offscreenIndex];
  }

  /**
   * オフスクリーンのオーナーインデックス配列を取得する
   * @return オフスクリーンのオーナーインデックス配列
   */
  public getOffscreenOwnerIndices(): Int32Array {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return new Int32Array(0);
    }

    return this.getCoreOffscreens().ownerIndices;
  }

  /**
   * オフスクリーンの不透明度を取得
   * @param offscreenIndex オフスクリーンのインデックス
   * @return 不透明度
   */
  public getOffscreenOpacity(offscreenIndex: number): number {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return 1.0;
    }

    const offscreens = this.getCoreOffscreens();
    if (offscreenIndex < 0 || offscreenIndex >= offscreens.count) {
      return 1.0; // オフスクリーンが無いのでスキップ
    }

    return offscreens.opacities[offscreenIndex];
  }

  /**
   * オフスクリーンのクリッピングマスクリストの取得
   * @return オフスクリーンのクリッピングマスクリスト
   */
  public getOffscreenMasks(): Int32Array[] {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return [];
    }

    return this.getCoreOffscreens().masks;
  }

  /**
   * オフスクリーンのクリッピングマスクの個数リストの取得
   * @return オフスクリーンのクリッピングマスクの個数リスト
   */
  public getOffscreenMaskCounts(): Int32Array {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return new Int32Array(0);
    }

    return this.getCoreOffscreens().maskCounts;
  }

  /**
   * オフスクリーンのマスク反転設定を取得する
   * @param offscreenIndex オフスクリーンのインデックス
   * @return オフスクリーンのマスク反転設定
   */
  public getOffscreenInvertedMask(offscreenIndex: number): boolean {
    const constantFlags: Uint8Array = this.getCoreOffscreens().constantFlags;
    // Live2DCubismCore.Utils.hasIsInvertedMaskBit を利用
    return Live2DCubismCore.Utils.hasIsInvertedMaskBit(
      constantFlags[offscreenIndex]
    );
  }

  /**
   * ブレンドモード使用判定
   * @return ブレンドモードを使用しているか
   */
  public isBlendModeEnabled(): boolean {
    if (DISABLE_ADVANCED_BLEND_AND_OFFSCREENS) {
      return false;
    }

    return this._isBlendModeEnabled;
  }

  /**
   * 保存されたパラメータの読み込み
   */
  public loadParameters(): void {
    let parameterCount: number = this.getCoreParameters().count;
    const savedParameterCount: number = this._savedParameters.length;

    if (parameterCount > savedParameterCount) {
      parameterCount = savedParameterCount;
    }

    for (let i = 0; i < parameterCount; ++i) {
      this._parameterValues[i] = this._savedParameters[i];
    }
  }

  /**
   * 初期化する
   */
  public initialize(): void {
    CSM_ASSERT(this._model);

    const parameters = this.getCoreParameters();
    const parts = this.getCoreParts();
    const drawables = this.getCoreDrawables();

    console.info('[pet-renderer] CubismModel.initialize()', {
      parameters: {
        count: parameters.count,
        ids: parameters.ids.length,
        values: parameters.values.length
      },
      parts: {
        count: parts.count,
        ids: parts.ids.length,
        opacities: parts.opacities.length
      },
      drawables: {
        count: drawables.count,
        ids: drawables.ids.length,
        constantFlags: drawables.constantFlags.length,
        dynamicFlags: drawables.dynamicFlags.length,
        blendModes: drawables.blendModes.length,
        parentPartIndices: drawables.parentPartIndices.length
      },
      offscreens: {
        count: this.getCoreOffscreens().count
      }
    });

    this._parameterValues = parameters.values;
    this._partOpacities = parts.opacities;
    this._offscreenOpacities = this.getCoreOffscreens().opacities;

    this._parameterMaximumValues = parameters.maximumValues;
    this._parameterMinimumValues = parameters.minimumValues;

    {
      const parameterIds: string[] = parameters.ids;
      const parameterCount: number = parameters.count;

      this._parameterIds.length = parameterCount;
      this._userParameterRepeatDataList.length = parameterCount;
      for (let i = 0; i < parameterCount; ++i) {
        this._parameterIds[i] = CubismFramework.getIdManager().getId(
          parameterIds[i]
        );
        this._userParameterRepeatDataList[i] = new ParameterRepeatData(
          false,
          false
        );
      }
    }

    const partCount: number = parts.count;
    {
      const partIds: string[] = parts.ids;

      this._partIds.length = partCount;
      for (let i = 0; i < partCount; ++i) {
        this._partIds[i] = CubismFramework.getIdManager().getId(partIds[i]);
      }
    }

    {
      const drawableIds: string[] = drawables.ids;
      const drawableCount: number = drawables.count;

      // Drawableカリング設定
      this._userDrawableCullings.length = drawableCount;
      const userCulling: CullingData = new CullingData(false, false);

      // Offscreenカリング設定
      this._userOffscreenCullings.length = this.getCoreOffscreens().count;
      const userOffscreenCulling: CullingData = new CullingData(false, false);

      // Drawables
      {
        for (let i = 0; i < drawableCount; ++i) {
          this._drawableIds.push(
            CubismFramework.getIdManager().getId(drawableIds[i])
          );

          this._userDrawableCullings[i] = userCulling;
        }
      }

      // Offscreens
      {
        for (let i = 0; i < this.getCoreOffscreens().count; ++i) {
          this._userOffscreenCullings[i] = userOffscreenCulling;
        }
      }

      // blendMode
      // オフスクリーンが存在するか、DrawableのブレンドモードでColorBlend、AlphaBlendを使用するのであればブレンドモードを有効にする。
      if (this.getOffscreenCount() > 0) {
        this._isBlendModeEnabled = true;
      } else {
        const blendModes = drawables.blendModes;
        for (let i = 0; i < drawableCount; ++i) {
          const colorBlendType = this.getDrawableColorBlend(i);
          const alphaBlendType = this.getDrawableAlphaBlend(i);

          // NormalOver、AddCompatible、MultiplyCompatible以外であればブレンドモードを有効にする。
          if (
            !(
              colorBlendType == CubismColorBlend.ColorBlend_Normal &&
              alphaBlendType == CubismAlphaBlend.AlphaBlend_Over
            ) &&
            colorBlendType != CubismColorBlend.ColorBlend_AddCompatible &&
            colorBlendType != CubismColorBlend.ColorBlend_MultiplyCompatible
          ) {
            this._isBlendModeEnabled = true;
            break;
          }
        }
      }

      this.setupPartsHierarchy();

      // CubismModelMultiplyAndScreenColorの初期化
      const offscreenCount = this.getOffscreenCount();
      this._overrideMultiplyAndScreenColor.initialize(
        partCount,
        drawableCount,
        offscreenCount
      );
    }
  }

  /**
   * パーツ階層構造を取得する
   * @return パーツ階層構造の配列
   */
  public getPartsHierarchy(): Array<CubismModelPartInfo> {
    return this._partsHierarchy;
  }

  /**
   * パーツ階層構造をセットアップする
   */
  public setupPartsHierarchy(): void {
    this._partsHierarchy.length = 0;

    // すべてのパーツのパーツ情報管理構造体を作成
    const partCount = this.getPartCount();
    this._partsHierarchy.length = partCount;
    for (let i = 0; i < partCount; ++i) {
      const partInfo = new CubismModelPartInfo();
      this._partsHierarchy[i] = partInfo;
    }

    // Partごとに親パーツを取得し、親パーツの子objectリストに追加する
    for (let i = 0; i < partCount; ++i) {
      const parentPartIndex = this.getPartParentPartIndices()[i];

      if (parentPartIndex === NoParentIndex) {
        continue;
      }

      for (
        let partIndex = 0;
        partIndex < this._partsHierarchy.length;
        ++partIndex
      ) {
        if (partIndex === parentPartIndex) {
          const objectInfo = new CubismModelObjectInfo(
            i,
            CubismModelObjectType.CubismModelObjectType_Parts
          );
          this._partsHierarchy[partIndex].objects.push(objectInfo);
          break;
        }
      }
    }

    // Drawableごとに親パーツを取得し、親パーツの子objectリストに追加する
    const drawableCount = this.getDrawableCount();
    for (let i = 0; i < drawableCount; ++i) {
      const parentPartIndex = this.getDrawableParentPartIndex(i);

      if (parentPartIndex === NoParentIndex) {
        continue;
      }

      for (
        let partIndex = 0;
        partIndex < this._partsHierarchy.length;
        ++partIndex
      ) {
        if (partIndex === parentPartIndex) {
          const objectInfo = new CubismModelObjectInfo(
            i,
            CubismModelObjectType.CubismModelObjectType_Drawable
          );
          this._partsHierarchy[partIndex].objects.push(objectInfo);
          break;
        }
      }
    }

    // パーツ子描画オブジェクト情報構造体を作成していく
    for (let i = 0; i < this._partsHierarchy.length; ++i) {
      // パーツ管理構造体を取得
      this.getPartChildDrawObjects(i);
    }
  }

  /**
   * 指定したパーツの子描画オブジェクト情報を取得・構築する
   * @param partInfoIndex パーツ情報のインデックス
   * @return PartChildDrawObjects
   */
  public getPartChildDrawObjects(partInfoIndex: number): PartChildDrawObjects {
    if (this._partsHierarchy[partInfoIndex].getChildObjectCount() < 1) {
      // 子オブジェクトがない場合
      return this._partsHierarchy[partInfoIndex].childDrawObjects;
    }

    const childDrawObjects =
      this._partsHierarchy[partInfoIndex].childDrawObjects;

    // 既にchildDrawObjectsが処理されている場合はスキップ
    if (
      childDrawObjects.drawableIndices.length !== 0 ||
      childDrawObjects.offscreenIndices.length !== 0
    ) {
      return childDrawObjects;
    }

    const objects = this._partsHierarchy[partInfoIndex].objects;

    for (let i = 0; i < objects.length; ++i) {
      const obj = objects[i];

      if (
        obj.objectType === CubismModelObjectType.CubismModelObjectType_Parts
      ) {
        // 子のパーツの場合、再帰的に子objectsを取得
        this.getPartChildDrawObjects(obj.objectIndex);

        // 子パーツの子Drawable、Offscreenを取得
        const childToChildDrawObjects =
          this._partsHierarchy[obj.objectIndex].childDrawObjects;

        childDrawObjects.drawableIndices.push(
          ...childToChildDrawObjects.drawableIndices
        );
        childDrawObjects.offscreenIndices.push(
          ...childToChildDrawObjects.offscreenIndices
        );

        // Offscreenの確認
        const offscreenIndices = this.getOffscreenIndices();
        const offscreenIndex = offscreenIndices
          ? offscreenIndices[obj.objectIndex]
          : NoOffscreenIndex;
        if (offscreenIndex !== NoOffscreenIndex) {
          childDrawObjects.offscreenIndices.push(offscreenIndex);
        }
      } else if (
        obj.objectType === CubismModelObjectType.CubismModelObjectType_Drawable
      ) {
        // Drawableの場合、パーツの子Drawableに追加
        childDrawObjects.drawableIndices.push(obj.objectIndex);
      }
    }

    return childDrawObjects;
  }

  /**
   * パーツのオフスクリーンインデックス配列を取得
   * @return Int32Array offscreenIndices
   */
  private getOffscreenIndices(): Int32Array {
    return (
      (this._model.parts as { offscreenIndices?: Int32Array }).offscreenIndices ??
      new Int32Array(this.getPartCount()).fill(NoOffscreenIndex)
    );
  }

  /**
   * コンストラクタ
   * @param model モデル
   */
  public constructor(model: Live2DCubismCore.Model) {
    this._model = model;
    this._parameterValues = null;
    this._parameterMaximumValues = null;
    this._parameterMinimumValues = null;
    this._partOpacities = null;
    this._offscreenOpacities = null;
    this._savedParameters = new Array<number>();
    this._parameterIds = new Array<CubismIdHandle>();
    this._drawableIds = new Array<CubismIdHandle>();
    this._partIds = new Array<CubismIdHandle>();
    this._isOverriddenParameterRepeat = true;
    this._isOverriddenCullings = false;
    this._modelOpacity = 1.0;

    // CubismModelMultiplyAndScreenColorのインスタンスを作成
    this._overrideMultiplyAndScreenColor =
      new CubismModelMultiplyAndScreenColor(this);

    this._isBlendModeEnabled = false;
    this._drawableColorBlends = null;
    this._drawableAlphaBlends = null;
    this._offscreenColorBlends = null;
    this._offscreenAlphaBlends = null;
    this._drawableMultiplyColors = null;
    this._drawableScreenColors = null;
    this._offscreenMultiplyColors = null;
    this._offscreenScreenColors = null;

    this._userParameterRepeatDataList = new Array<ParameterRepeatData>();
    this._userDrawableCullings = new Array<CullingData>();
    this._userOffscreenCullings = new Array<CullingData>();
    this._partsHierarchy = new Array<CubismModelPartInfo>();

    this._notExistPartId = new Map<CubismIdHandle, number>();
    this._notExistParameterId = new Map<CubismIdHandle, number>();
    this._notExistParameterValues = new Map<number, number>();
    this._notExistPartOpacities = new Map<number, number>();

    // Drawableのカラーブレンドとアルファブレンドの初期化
    this._drawableColorBlends = new Array<CubismColorBlend>(
      this.getCoreDrawables().count
    ).fill(CubismColorBlend.ColorBlend_None);
    this._drawableAlphaBlends = new Array<CubismAlphaBlend>(
      this.getCoreDrawables().count
    ).fill(CubismAlphaBlend.AlphaBlend_None);

    // Offscreenのカラーブレンドとアルファブレンドの初期化
    this._offscreenColorBlends = new Array<CubismColorBlend>(
      (((model as Live2DCubismCore.Model & { offscreens?: { count?: number } }).offscreens?.count) ?? 0)
    ).fill(CubismColorBlend.ColorBlend_None);
    this._offscreenAlphaBlends = new Array<CubismAlphaBlend>(
      (((model as Live2DCubismCore.Model & { offscreens?: { count?: number } }).offscreens?.count) ?? 0)
    ).fill(CubismAlphaBlend.AlphaBlend_None);
  }

  /**
   * デストラクタ相当の処理
   */
  public release(): void {
    this._model.release();
    this._model = null;

    this._drawableColorBlends = null;
    this._drawableAlphaBlends = null;
    this._offscreenColorBlends = null;
    this._offscreenAlphaBlends = null;

    this._drawableMultiplyColors = null;
    this._drawableScreenColors = null;
    this._offscreenMultiplyColors = null;
    this._offscreenScreenColors = null;
  }

  private _notExistPartOpacities: Map<number, number>; // 存在していないパーツの不透明度のリスト
  private _notExistPartId: Map<CubismIdHandle, number>; // 存在していないパーツIDのリスト

  private _notExistParameterValues: Map<number, number>; // 存在していないパラメータの値のリスト
  private _notExistParameterId: Map<CubismIdHandle, number>; // 存在していないパラメータIDのリスト

  private _savedParameters: Array<number>; // 保存されたパラメータ

  /**
   * Flag to determine whether to override model-wide parameter repeats on the SDK
   */
  private _isOverriddenParameterRepeat: boolean;

  private _overrideMultiplyAndScreenColor: CubismModelMultiplyAndScreenColor; // 乗算色・スクリーン色の管理クラス

  /**
   * List to manage ParameterRepeat and Override flag to be set for each Parameter
   */
  private _userParameterRepeatDataList: Array<ParameterRepeatData>;
  private _partsHierarchy: Array<CubismModelPartInfo>; // Partの親子構造

  private _model: Live2DCubismCore.Model; // モデル

  private _parameterValues: Float32Array; // パラメータの値のリスト
  private _parameterMaximumValues: Float32Array; // パラメータの最大値のリスト
  private _parameterMinimumValues: Float32Array; // パラメータの最小値のリスト

  private _partOpacities: Float32Array; // パーツの不透明度のリスト
  private _offscreenOpacities: Float32Array; // オフスクリーンの不透明度のリスト

  private _modelOpacity: number; // モデルの不透明度

  private _parameterIds: Array<CubismIdHandle>;
  private _partIds: Array<CubismIdHandle>;
  private _drawableIds: Array<CubismIdHandle>;

  private _isOverriddenCullings: boolean; // モデルのカリング設定をすべて上書きするか？
  private _userDrawableCullings: Array<CullingData>; // カリング設定の配列
  private _userOffscreenCullings: Array<CullingData>; // オフスクリーンのカリング設定を使用するか？

  private _isBlendModeEnabled: boolean; // ブレンドモードを使用しているか

  private _drawableColorBlends: CubismColorBlend[]; // Drawableのカラーブレンドの配列
  private _drawableAlphaBlends: CubismAlphaBlend[]; // Drawableのアルファブレンドの配列
  private _offscreenColorBlends: CubismColorBlend[]; // Offscreen のカラーブレンドの配列
  private _offscreenAlphaBlends: CubismAlphaBlend[]; // Offscreen のアルファブレンドの配列

  private _drawableMultiplyColors: CubismTextureColor[]; // Drawableの乗算色の配列
  private _drawableScreenColors: CubismTextureColor[]; // Drawableのスクリーン色の配列
  private _offscreenMultiplyColors: CubismTextureColor[]; // Offscreenの乗算色の配列
  private _offscreenScreenColors: CubismTextureColor[]; // Offscreenのスクリーン色の配列
}

// Namespace definition for compatibility.
import * as $ from './cubismmodel';
// eslint-disable-next-line @typescript-eslint/no-namespace
export namespace Live2DCubismFramework {
  export const CubismModel = $.CubismModel;
  export type CubismModel = $.CubismModel;
}
