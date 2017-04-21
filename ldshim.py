#!/usr/bin/env python
def parseconf(confpath):
    import os.path
    confdir = os.path.dirname(confpath)
    f = open(confpath)
    dirs = []
    for line in f:
        f = line.find('#') #strip comments
        if f != -1:
            line = line[:f]
        f = line.find('=') #I don't know what = means, but binutils strips it
        if f != -1:
            line = line[:f]
        line = line.strip() #strip whitespace
        if line.startswith('include ') or line.startswith('include\t'):
            includeglob = line[8:].strip()
            if not includeglob.startswith(os.path.sep):
                includeglob = os.path.join(confdir,includeglob)
            import glob
            for fname in glob.glob(includeglob):
                dirs.extend(parseconf(fname))            
        elif line.startswith(os.path.sep):
            dirs.append(line)
        else:
            dirs.append(os.path.join(confdir,line))
    return dirs

def getlinuxdirs():
    dirs = ['/lib','/usr/lib']
    dirs.extend(parseconf('/etc/ld.so.conf'))
    return dirs

def makepathstring(L):
    return ':'.join(L)

def addldpaths(dirs):
    import os
    paths = getlinuxdirs()
    paths.extend(dirs)
    os.environ['LD_LIBRARY_PATH'] = makepathstring(paths)

if __name__ == "__main__":
    import os
    import sys
    base = os.environ['SUGAR_BUNDLE_PATH']
    print("The base path is %s" % base)
    sys.path.append(os.path.join(base,'usr/lib/python2.5/site-packages'))
    addldpaths([os.path.join(base,'usr/lib')]) #Sets LD_LIBRARY_PATH
    os.environ['PYTHONPATH'] = ':'.join(sys.path) #Sets PYTHONPATH
    os.environ['PATH'] += ":%s" % os.path.join(base,'usr/bin') #Extend PATH

    import subprocess
    subprocess.Popen(sys.argv[1:]) #Inherits the environment variables
