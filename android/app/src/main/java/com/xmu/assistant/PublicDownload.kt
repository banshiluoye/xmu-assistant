package com.xmu.assistant

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File

/** Android 10+ scoped downloads: visible in Files without broad storage permissions. */
internal fun publishPublicDownload(context:Context,file:File,directories:List<String>) {
    if(Build.VERSION.SDK_INT<29) return
    val resolver=context.contentResolver
    val values=ContentValues().apply {
        put(MediaStore.Downloads.DISPLAY_NAME,file.name)
        put(MediaStore.Downloads.MIME_TYPE,java.net.URLConnection.guessContentTypeFromName(file.name) ?: "application/octet-stream")
        put(MediaStore.Downloads.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/虾大助手/"+directories.map(::safeCoursewareSegment).joinToString("/")+"/")
        put(MediaStore.Downloads.IS_PENDING,1)
    }
    val uri=checkNotNull(resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values)){"无法创建系统下载文件"}
    try {
        checkNotNull(resolver.openOutputStream(uri)).use {output->file.inputStream().use {input->input.copyTo(output)}}
        check(resolver.update(uri,ContentValues().apply {put(MediaStore.Downloads.IS_PENDING,0)},null,null)>0) {"无法完成系统下载文件保存"}
    } catch(error:Exception) {resolver.delete(uri,null,null);throw error}
}
