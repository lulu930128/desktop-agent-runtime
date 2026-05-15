from typing import ClassVar, Dict

from pydantic import Field, model_validator

from .agent import AgentConfig
from .asr import ASRConfig
from .i18n import Description, I18nMixin
from .tts import TTSConfig
from .tts_preprocessor import TTSPreprocessorConfig
from .vad import VADConfig


class CharacterConfig(I18nMixin):
    """Character configuration settings."""

    conf_name: str = Field(..., alias="conf_name")
    conf_uid: str = Field(..., alias="conf_uid")
    live2d_model_name: str = Field(..., alias="live2d_model_name")
    character_name: str = Field(default="", alias="character_name")
    human_name: str = Field(default="Human", alias="human_name")
    avatar: str = Field(default="", alias="avatar")
    persona_prompt: str = Field(default="", alias="persona_prompt")
    persona_prompt_path: str = Field(default="", alias="persona_prompt_path")
    default_project_id: str = Field(default="", alias="default_project_id")
    active_project_id: str = Field(default="", alias="active_project_id")
    active_project_name: str = Field(default="", alias="active_project_name")
    active_project_root: str = Field(default="", alias="active_project_root")
    project_prompt_path: str = Field(default="", alias="project_prompt_path")
    tool_prompt_path: str = Field(default="", alias="tool_prompt_path")
    response_style_prompt_path: str = Field(
        default="", alias="response_style_prompt_path"
    )
    agent_config: AgentConfig = Field(..., alias="agent_config")
    asr_config: ASRConfig = Field(..., alias="asr_config")
    tts_config: TTSConfig = Field(..., alias="tts_config")
    vad_config: VADConfig = Field(..., alias="vad_config")
    tts_preprocessor_config: TTSPreprocessorConfig = Field(
        ..., alias="tts_preprocessor_config"
    )

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "conf_name": Description(
            en="Name of the character configuration",
            zh="角色配置名稱",
        ),
        "conf_uid": Description(
            en="Unique identifier for the character configuration",
            zh="角色配置唯一識別碼",
        ),
        "live2d_model_name": Description(
            en="Name of the Live2D model to use",
            zh="Live2D 模型名稱",
        ),
        "character_name": Description(
            en="Name of the AI character in conversation",
            zh="對話中角色名稱",
        ),
        "human_name": Description(
            en="Name of the human user in conversation",
            zh="對話中的使用者名稱",
        ),
        "avatar": Description(
            en="Avatar image path for the character",
            zh="角色頭像路徑",
        ),
        "persona_prompt": Description(
            en="Inline persona prompt for the character",
            zh="內嵌角色 prompt",
        ),
        "persona_prompt_path": Description(
            en="External persona prompt file path",
            zh="外部角色 prompt 路徑",
        ),
        "default_project_id": Description(
            en="Default launcher project for this character",
            zh="角色預設專案 ID",
        ),
        "active_project_id": Description(
            en="Selected project identifier",
            zh="目前選中的專案 ID",
        ),
        "active_project_name": Description(
            en="Selected project display name",
            zh="目前選中的專案名稱",
        ),
        "active_project_root": Description(
            en="Selected project root path",
            zh="目前選中的專案根目錄",
        ),
        "project_prompt_path": Description(
            en="Project-context prompt path",
            zh="專案 prompt 路徑",
        ),
        "tool_prompt_path": Description(
            en="Tool-use prompt path",
            zh="工具 prompt 路徑",
        ),
        "response_style_prompt_path": Description(
            en="Optional response-style prompt path",
            zh="回覆風格 prompt 路徑",
        ),
        "agent_config": Description(
            en="Configuration for the conversation agent",
            zh="對話代理設定",
        ),
        "asr_config": Description(
            en="Configuration for Automatic Speech Recognition",
            zh="語音辨識設定",
        ),
        "tts_config": Description(
            en="Configuration for Text-to-Speech",
            zh="語音合成設定",
        ),
        "vad_config": Description(
            en="Configuration for Voice Activity Detection",
            zh="VAD 設定",
        ),
        "tts_preprocessor_config": Description(
            en="Configuration for Text-to-Speech preprocessor",
            zh="TTS 前處理設定",
        ),
    }

    @model_validator(mode="after")
    def finalize_character_config(self):
        if not self.character_name:
            self.character_name = self.conf_name
        if not (self.persona_prompt or self.persona_prompt_path):
            raise ValueError(
                "Either persona_prompt or persona_prompt_path must be provided."
            )
        return self
