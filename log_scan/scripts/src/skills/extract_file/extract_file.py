import os
import zipfile
import tarfile
import gzip
import shutil

class ExtractFile:
    def __init__(self):
        pass

    def extract(self, input_path: str, output_path: str):
        # 检查log_path是否是压缩包，如果是则解压
        if self._is_archive_file(input_path):
            print(f"[INFO] 检测到压缩包: {input_path}")
            print(f"[INFO] 正在解压到目录: {input_path}")
            
            success = self._extract_archive(input_path, output_path)
            if not success:
                print(f"[ERROR] 解压失败: {output_path}")
                # 继续执行，可能log_dir中已有日志文件
            else:
                print(f"[INFO] 解压完成: {input_path} -> {output_path}")
        else:
            print(f"[INFO] 使用日志文件: {input_path}")
            # 如果是单个日志文件，复制到log_dir目录
            if os.path.isfile(input_path):
                dest_path = os.path.join(output_path, os.path.basename(input_path))
                try:
                    shutil.copy2(input_path, dest_path)
                    print(f"[INFO] 复制日志文件: {input_path} -> {dest_path}")
                except Exception as e:
                    print(f"[WARN] 复制日志文件失败: {e}")

    def _is_archive_file(self, file_path: str) -> bool:
        """
        检查文件是否是支持的压缩包格式
        
        支持格式:
            - .zip
            - .tar.gz, .tgz
            - .tar.bz2, .tbz2
            - .tar.xz, .txz
            - .tar
            - .gz
            - .7z
        """
        if not os.path.isfile(file_path):
            return False
        
        archive_extensions = {
            '.zip', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2',
            '.tar.xz', '.txz', '.tar', '.gz', '.7z'
        }
        
        # 检查文件扩展名
        file_path_lower = file_path.lower()
        for ext in archive_extensions:
            if file_path_lower.endswith(ext):
                return True
        
        return False
    
    def _extract_archive(self, archive_path: str, extract_dir: str) -> bool:
        """
        解压压缩包到指定目录
        
        参数:
            archive_path: 压缩包文件路径
            extract_dir: 解压目标目录
            
        返回:
            bool: 解压是否成功
        """
        if not os.path.isfile(archive_path):
            print(f"[ERROR] 压缩包文件不存在: {archive_path}")
            return False
        
        # 确保目标目录存在
        os.makedirs(extract_dir, exist_ok=True)
        
        archive_path_lower = archive_path.lower()
        
        try:
            # ZIP格式
            if archive_path_lower.endswith('.zip'):
                return self._extract_zip(archive_path, extract_dir)
            
            # TAR格式（包括压缩的tar）
            elif any(archive_path_lower.endswith(ext) for ext in ['.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.tar']):
                return self._extract_tar(archive_path, extract_dir)
            
            # GZIP格式（纯gzip）
            elif archive_path_lower.endswith('.gz'):
                return self._extract_gzip(archive_path, extract_dir)
            
            # 7Z格式
            elif archive_path_lower.endswith('.7z'):
                return self._extract_7z(archive_path, extract_dir)
            
            else:
                print(f"[ERROR] 不支持的压缩格式: {archive_path}")
                return False
                
        except Exception as e:
            print(f"[ERROR] 解压过程中发生错误: {e}")
            return False
    
    def _extract_zip(self, zip_path: str, extract_dir: str) -> bool:
        """解压ZIP文件"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # 获取文件列表
                file_list = zip_ref.namelist()
                print(f"[INFO] ZIP包中包含 {len(file_list)} 个文件")
                
                temp_dir = os.path.join(extract_dir, "_temp_zip_extract")
                os.makedirs(temp_dir, exist_ok=True)
                zip_ref.extractall(temp_dir)
                self._move_dir(temp_dir, extract_dir)
                os.rmdir(temp_dir)
                
                # 统计解压的文件类型
                extracted_files = [f for f in file_list if not f.endswith('/')]
                log_files = [f for f in extracted_files if f.lower().endswith('.log')]
                print(f"[INFO] 解压完成，共解压 {len(extracted_files)} 个文件，其中包含 {len(log_files)} 个日志文件")
                return True
                
        except zipfile.BadZipFile as e:
            print(f"[ERROR] ZIP文件损坏: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] 解压ZIP文件失败: {e}")
            return False
        
    def _extract_tar(self, tar_path: str, extract_dir: str) -> bool:
        """解压TAR文件（支持多种压缩格式）"""
        try:
            # 根据扩展名确定打开模式
            if tar_path.lower().endswith('.tar.gz') or tar_path.lower().endswith('.tgz'):
                mode = 'r:gz'
            elif tar_path.lower().endswith('.tar.bz2') or tar_path.lower().endswith('.tbz2'):
                mode = 'r:bz2'
            elif tar_path.lower().endswith('.tar.xz') or tar_path.lower().endswith('.txz'):
                mode = 'r:xz'
            else:  # .tar
                mode = 'r'
            
            with tarfile.open(tar_path, mode) as tar_ref:
                # 获取文件列表
                members = tar_ref.getmembers()
                print(f"[INFO] TAR包中包含 {len(members)} 个文件/目录")
                
                temp_dir = os.path.join(extract_dir, "_temp_zip_extract")
                os.makedirs(temp_dir, exist_ok=True)
                tar_ref.extractall(temp_dir)
                self._move_dir(temp_dir, extract_dir)
                os.rmdir(temp_dir)
                
                # 统计解压的文件类型
                log_files = [m.name for m in members if m.isfile() and m.name.lower().endswith('.log')]
                print(f"[INFO] 解压完成，其中包含 {len(log_files)} 个日志文件")
                return True
                
        except tarfile.ReadError as e:
            print(f"[ERROR] TAR文件读取错误: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] 解压TAR文件失败: {e}")
            return False

    def _extract_gzip(self, gz_path: str, extract_dir: str) -> bool:
        """解压GZIP文件"""
        try:
            # 获取解压后的文件名（去掉.gz扩展名）
            base_name = os.path.basename(gz_path)
            if base_name.lower().endswith('.gz'):
                output_name = base_name[:-3]
            else:
                output_name = base_name + '_decompressed'
            
            output_path = os.path.join(extract_dir, output_name)
            
            with gzip.open(gz_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            print(f"[INFO] GZIP解压完成: {base_name} -> {output_name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] 解压GZIP文件失败: {e}")
            return False

    def _extract_7z(self, sevenz_path: str, extract_dir: str) -> bool:
        """解压7Z文件（需要安装py7zr库）"""
        try:
            # 尝试导入py7zr
            import py7zr
            
            with py7zr.SevenZipFile(sevenz_path, mode='r') as sevenz_ref:
                # 获取文件列表
                file_list = sevenz_ref.getnames()
                print(f"[INFO] 7Z包中包含 {len(file_list)} 个文件")
                
                temp_dir = os.path.join(extract_dir, "_temp_zip_extract")
                os.makedirs(temp_dir, exist_ok=True)
                sevenz_ref.extractall(temp_dir)
                self._move_dir(temp_dir, extract_dir)
                os.rmdir(temp_dir)

                # 统计解压的文件类型
                log_files = [f for f in file_list if f.lower().endswith('.log')]
                print(f"[INFO] 解压完成，其中包含 {len(log_files)} 个日志文件")
                return True
                
        except ImportError:
            print(f"[ERROR] 解压7Z文件需要安装py7zr库，请执行: pip install py7zr")
            return False
        except Exception as e:
            print(f"[ERROR] 解压7Z文件失败: {e}")
            return False
        
    def _move_dir(self, temp_dir: str, extract_dir: str):
        temp_items = os.listdir(temp_dir)
        # 如果只有一个项目且是目录，则将其内容移动到extract_dir
        if len(temp_items) == 1 and os.path.isdir(os.path.join(temp_dir, temp_items[0])):
            root_dir = os.path.join(temp_dir, temp_items[0])
            print(f"[INFO] 检测到根目录 '{temp_items[0]}'，将去掉根目录")
            
            for item in os.listdir(root_dir):
                src = os.path.join(root_dir, item)
                dst = os.path.join(extract_dir, item)
                shutil.move(src, dst)
            os.rmdir(root_dir)
        else:
            # 没有根目录，直接移动所有文件
            for item in temp_items:
                src = os.path.join(temp_dir, item)
                dst = os.path.join(extract_dir, item)
                shutil.move(src, dst)