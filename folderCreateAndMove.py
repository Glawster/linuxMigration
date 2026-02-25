import os
import tqdm

def identifyCommonString(folderPath):
    stringList = []
    filesCount = 0
    for root, dirs, files in os.walk(folderPath):
        for name in dirs + files:
            filesCount += 1

    # create a progress bar
    with tqdm.tqdm(total=filesCount) as pbar:
    
        for root, dirs, files in os.walk(folderPath):
            for name in dirs + files:
                pbar.update(1)

                # strip the extension from name if there is one and name is a file
                if os.path.isfile(os.path.join(root, name)):
                    name, _ = os.path.splitext(name)

                # using name look at all the other folders or files and see if there is a common string between name and all the other folders or files
                for root2, dirs2, files2 in os.walk(folderPath):
                    for name2 in dirs2 + files2:

                        # strip the extension from name2 if there is one
                        if os.path.isfile(os.path.join(root2, name2)):
                            name2, _ = os.path.splitext(name2)

                        if name == name2:
                            continue

                        # get the string in name up to the first '.' in name
                        thisName = name.split('.')[0]
                        thisName2 = name2.split('.')[0]

                        # if name or name2 includes ' - ' then split the string at ' - ' and take the first part
                        if ' - ' in thisName:
                            thisName = thisName.split(' - ')[0]
                        if ' - ' in thisName2:
                            thisName2 = thisName2.split(' - ')[0]

                        commonString = os.path.commonprefix([thisName, thisName2])  

                        if len(commonString) < 3:
                            continue

                        # add commonString to a list of common strings unless it is already in the list
                        if commonString not in stringList:
                            stringList.append(commonString)
    return stringList

# Example usage
folderPath = 'Y:\Pron\Other'
stringList = identifyCommonString(folderPath)

# from common strings identify a string that is a substring of another common string, keep only the larger string
for commonString in stringList:
    for commonString2 in stringList:
        if commonString in commonString2 and commonString != commonString2:
            try:
                stringList.remove(commonString)
            except ValueError:
                pass

# for each common string, create a folder and move all files with that common string in the name to that folder
for commonString in stringList:

    folderName = os.path.join(folderPath, commonString)
    
    if not os.path.exists(folderName):
        os.makedirs(folderName)

    # for just the top level of the folderPath
    fileList = os.listdir(folderPath)
    for file in fileList:
        if commonString in file:
            if commonString == file:
                continue
            os.rename(os.path.join(folderPath, file), os.path.join(folderName, file))