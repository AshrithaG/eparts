Two files that together give you the training pairs you need:
1A_Product_Attribute_Pairs -- Each row is one (product, attribute, value) triple. Columns include Product_ID, Product_Number, Manufacturer_Name, ProductType_Name, Short_Description, Full_Description, Extended_Description, Attribute_Name, Attribute_Value, DisplayText, Unit_Suffix, DigitalValue, RangeLow, RangeHigh. The description columns are what our product team wrote after reviewing spec sheets -- treat these as the "input text." The attribute columns are the verified mappings -- treat these as the "output labels."
1A_Product_Document_Links -- Each row links a Product_ID to a spec sheet or image URL (DocumentLocation). Join on Product_ID to the attribute pairs file. These URLs point to the actual PDFs and images our team used as source material -- feed these into your OCR pipeline and compare what you extract against the verified attribute values. ImageFile = 1 means it's an image, 0 means it's a document (PDF/spec sheet).
1B. Products Master Table
1B_Product_Master -- Full product catalog: Product_ID, Product_Number, Product_Name, Short_Description, Full_Description, Extended_Description, Manufacturer_ID/Name, ProductType_ID/Name, Category_ID, Weight, Quantity, Tariff Code. This is the reference library your similarity model searches against. This is the full active catalog.
1C. Staging Schema
I think this will mainly be a part of understanding PIMS, and based off of it we can send you the appropriate information.
2A. Valid Values per Attribute
2A_Values_Per_Attribute -- Every distinct (Attribute_Name, Value, Unit_Suffix) combination currently in production, with a Usage_Count showing how often it appears. 
2B. Historical Edit Cases
2B_Apparent_Correction_Cases -- Products that went through multiple edit events, with dates and edit reasons. Products with Edit_Count > 1 were re-edited (likely corrections). There's no formal error-tracking system, so this is the best proxy.