"""Конфигурация сервера."""
import yaml
import os
from typing import Dict, Any


class Config:
    """Класс для управления конфигурацией."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Инициализация конфигурации."""
        self.config_path = config_path
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из файла."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Конфигурационный файл {self.config_path} не найден")
        except yaml.YAMLError as e:
            raise ValueError(f"Ошибка парсинга YAML: {e}")
    
    @property
    def server(self) -> Dict[str, Any]:
        """Настройки сервера."""
        return self._config.get('server', {})
    
    @property
    def database(self) -> Dict[str, Any]:
        """Настройки базы данных."""
        return self._config.get('database', {})
    
    @property
    def api(self) -> Dict[str, Any]:
        """Настройки API."""
        return self._config.get('api', {})
    
    @property
    def logging(self) -> Dict[str, Any]:
        """Настройки логирования."""
        return self._config.get('logging', {})
    
    @property
    def protocol(self) -> Dict[str, Any]:
        """Настройки протокола."""
        return self._config.get('protocol', {})
    
    def get_database_url(self) -> str:
        """Получение URL для подключения к базе данных."""
        db_config = self.database
        return (
            f"postgresql://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['name']}"
        )


# Глобальный экземпляр конфигурации
config = Config()

